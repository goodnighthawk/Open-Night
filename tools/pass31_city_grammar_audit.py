from __future__ import annotations

import argparse
import csv
from collections import Counter, defaultdict
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"dev_tools"/"map_generator"/"profiles"/"gwb_gameplay"/"unified_composition"
SEM=OUT/"semantic"
RULES_PATH=ROOT/"config"/"city_art_rules.csv"
ASSIGN=SEM/"pass31_city_grammar_assignments.csv"
BUILDINGS=SEM/"pass29_extension_buildings.csv"
OPEN=SEM/"pass29_extension_open_blocks.csv"


def table(path):
    with Path(path).open("r",encoding="utf-8-sig",newline="") as f:return list(csv.DictReader(f))


def rules():return {r["rule_id"]:r for r in table(RULES_PATH)}

def bounds(rs,key):
    r=rs[key];return float(r["target_min"]),float(r["target_max"])

def kv(path):return {r["key"]:r["value"] for r in table(path)}


def main():
    ap=argparse.ArgumentParser();ap.add_argument("--strict",action="store_true");args=ap.parse_args()
    problems=[];rs=rules();m=kv(OUT/"composition_manifest.csv")
    if m.get("pass_id")!="pass_31_city_grammar_rc1":problems.append(f"pass_id={m.get('pass_id')!r}")
    if m.get("pass31_city_grammar")!="approved_core_v1":problems.append("city grammar manifest contract missing")
    if not ASSIGN.is_file():problems.append("missing pass31 assignment table")
    if problems:
        print("PASS31_CITY_GRAMMAR_GATE=FAIL")
        for p in problems:print(" - "+p)
        return 1

    a=table(ASSIGN);b=table(BUILDINGS);opens=table(OPEN)
    if len(a)!=len(b):problems.append(f"assignment/building row mismatch {len(a)}/{len(b)}")
    ids=[r["building_id"] for r in a]
    if len(ids)!=len(set(ids)):problems.append("duplicate building ids in grammar assignments")
    n=max(1,len(a))

    merged=sum(int(float(r["merged_lot_count"]))>=2 for r in a)/n
    irregular=sum(r["massing_variant"]!="rect" for r in a)/n
    shapes=Counter(r["massing_variant"] for r in a);max_shape=max(shapes.values(),default=0)/n
    blocks=defaultdict(list);districts=defaultdict(list);runs=Counter()
    for r in a:
        blocks[r["block_id"]].append(r);districts[r["material_family"].rsplit("_family_",1)[0]].append(r);runs[r["frontage_run_id"]]+=1

    height_match=height_total=0
    for rows in blocks.values():
        if len(rows)<2:continue
        c=Counter(r["height_band"] for r in rows);height_match+=max(c.values());height_total+=len(rows)
    height_cluster=height_match/max(1,height_total)
    run_target=sum(2<=v<=6 for v in runs.values())/max(1,len(runs))
    active_material={d:len(set(r["material_family"] for r in rows)) for d,rows in districts.items()}
    material_repeat={}
    for d,rows in districts.items():
        c=Counter(r["material_family"] for r in rows);material_repeat[d]=max(c.values())/max(1,len(rows))

    open_share=len(opens)/max(1,len(opens)+len(b))
    lo,hi=bounds(rs,"block_merged_lot_share")
    if not lo<=merged<=hi:problems.append(f"merged share {merged:.3f} outside {lo:.3f}..{hi:.3f}")
    lo,hi=bounds(rs,"building_irregular_shape")
    if not lo<=irregular<=hi:problems.append(f"irregular massing share {irregular:.3f} outside {lo:.3f}..{hi:.3f}")
    _,hi=bounds(rs,"building_shape_dominance")
    if max_shape>hi:problems.append(f"dominant shape share {max_shape:.3f} > {hi:.3f} ({shapes.most_common(1)})")
    lo,hi=bounds(rs,"block_height_cluster")
    if height_total and not lo<=height_cluster<=hi:problems.append(f"height cluster share {height_cluster:.3f} outside {lo:.3f}..{hi:.3f}")
    lo,hi=bounds(rs,"art_material_family")
    for district,count in active_material.items():
        if not lo<=count<=hi:problems.append(f"{district} active material families={count}, expected {lo:g}..{hi:g}")
    # Open-space rows are a conservative subset because large authored parks are
    # separate geometry. Never fail for being above the minimum merely on this ratio.
    open_lo,_=bounds(rs,"block_open_space_share")
    if open_share<open_lo*0.55:problems.append(f"catalogued intentional-open share {open_share:.3f} too low")

    # Attached-run length is a soft design rule, but strict Pass 31 requires at
    # least a useful plurality of 2–6-building runs so the extension cannot read
    # as uniformly isolated parcels again.
    if args.strict and run_target<0.30:problems.append(f"only {run_target:.1%} frontage-run groups contain 2..6 buildings")
    if args.strict and len(a)<220:problems.append(f"extension too sparse after grammar generation: {len(a)} buildings")
    if args.strict and len(blocks)<35:problems.append(f"too few distinct urban grammar blocks: {len(blocks)}")

    print(
        "PASS31_CITY_GRAMMAR_AUDIT "
        f"buildings={len(a)} blocks={len(blocks)} runs={len(runs)} run_target_share={run_target:.3f} "
        f"merged={merged:.3f} irregular={irregular:.3f} max_shape={max_shape:.3f} height_cluster={height_cluster:.3f} "
        f"open_catalog_share={open_share:.3f} materials={active_material} material_max_share={material_repeat} shapes={dict(shapes)}"
    )
    if problems:
        print("PASS31_CITY_GRAMMAR_GATE=FAIL")
        for p in problems:print(" - "+p)
        return 1
    print("PASS31_CITY_GRAMMAR_GATE=PASS")
    return 0


if __name__=="__main__":raise SystemExit(main())
