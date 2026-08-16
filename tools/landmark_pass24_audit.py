from __future__ import annotations

import argparse
import csv
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SEM=ROOT/"dev_tools"/"map_generator"/"profiles"/"gwb_gameplay"/"unified_composition"/"semantic"


def rows(path):
    with Path(path).open("r",encoding="utf-8-sig",newline="") as f:return list(csv.DictReader(f))


def main():
    ap=argparse.ArgumentParser();ap.add_argument("--strict",action="store_true");args=ap.parse_args()
    landmarks=rows(SEM/"landmarks_pass24.csv")
    buildings=rows(SEM/"iterated_buildings.csv")
    by_id={b["id"]:b for b in buildings}

    bridge=[r for r in landmarks if r["district"]=="bridge"]
    churches=[r for r in landmarks if r["kind"]=="church"]
    building_marks=[r for r in landmarks if r["district"]!="bridge"]
    subjects=[r["subject_id"] for r in building_marks]
    duplicate_subjects=sorted({s for s in subjects if subjects.count(s)>1})

    missing_parent=[];outside_parent=[]
    for r in building_marks:
        b=by_id.get(r["subject_id"])
        if b is None:
            missing_parent.append(r["landmark_id"]);continue
        rx,ry,rw,rh=map(float,(r["x"],r["y"],r["w"],r["h"]))
        bx,by,bw,bh=map(float,(b["x"],b["y"],b["w"],b["h"]))
        if rx < bx-1e-6 or ry < by-1e-6 or rx+rw > bx+bw+1e-6 or ry+rh > by+bh+1e-6:
            outside_parent.append(r["landmark_id"])

    bridge_corridor_bad=[]
    for r in bridge:
        x,y,w,h=map(float,(r["x"],r["y"],r["w"],r["h"]))
        if x < 4300 or x+w > 11100 or y < 5600 or y+h > 6800:
            bridge_corridor_bad.append(r["landmark_id"])

    roles={r["visual_role"] for r in landmarks}
    church_roles={r["visual_role"] for r in churches}
    # Two physical bridge tower rows intentionally read as one landmark group.
    grouped_count=len(landmarks)-1 if sum(r["kind"]=="bridge_tower" for r in bridge)==2 else len(landmarks)
    districts={r["district"] for r in landmarks}

    print("PASS24_LANDMARK_AUDIT "
          f"rows={len(landmarks)} recognizable_groups={grouped_count} roles={len(roles)} "
          f"bridge={len(bridge)} building={len(building_marks)} churches={len(churches)} "
          f"church_roles={len(church_roles)} duplicate_subjects={len(duplicate_subjects)} "
          f"missing_parent={len(missing_parent)} outside_parent={len(outside_parent)} bridge_corridor_bad={len(bridge_corridor_bad)}")
    if not args.strict:return 0
    problems=[]
    if not 8 <= grouped_count <= 12:problems.append(f"recognizable landmark groups {grouped_count} not in 8..12")
    if len(bridge)!=4:problems.append(f"expected four GWB physical landmark elements, got {len(bridge)}")
    if len(churches)!=3 or len(church_roles)!=3:problems.append("three churches are not all distinctly treated")
    if len(building_marks)<8:problems.append(f"only {len(building_marks)} building landmarks")
    if duplicate_subjects:problems.append(f"building landmark subjects repeated: {duplicate_subjects}")
    if missing_parent:problems.append(f"landmarks missing building parent: {missing_parent}")
    if outside_parent:problems.append(f"building landmark bounds exceed parent footprint: {outside_parent}")
    if bridge_corridor_bad:problems.append(f"bridge landmark bounds leave GWB corridor: {bridge_corridor_bad}")
    if not {"fort_lee","washington_heights","bridge"}.issubset(districts):problems.append(f"landmark district coverage incomplete: {districts}")
    if problems:
        print("PASS24_LANDMARK_GATE=FAIL")
        for p in problems:print(" - "+p)
        return 1
    print("PASS24_LANDMARK_GATE=PASS");return 0

if __name__=="__main__":raise SystemExit(main())
