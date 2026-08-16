from __future__ import annotations

"""Pass 25: final visual convergence audit bundle.

This pass intentionally freezes Pass 24 visual content. It regenerates the complete
map deterministically, records convergence metrics, creates a fixed screenshot suite
at stable coordinates, and updates the manifest. No geometry or visual placement is
changed after Pass 24.
"""

import csv
import math
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import build_pass20_streetwall as pass20
import build_pass24_landmarks as pass24

PASS_ID = "pass_25_final_visual_convergence_rc1"
REPO = Path(__file__).resolve().parents[3]
QA_DIR = REPO / "qa"
SCREENSHOT_DIR = QA_DIR / "pass25_screenshots"
CONVERGENCE_CSV = QA_DIR / "map_visual_convergence.csv"


def read_csv(path: Path):
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_metrics(rows):
    QA_DIR.mkdir(parents=True, exist_ok=True)
    with CONVERGENCE_CSV.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=("metric", "value", "target", "status", "notes"))
        writer.writeheader();writer.writerows(rows)


def centre(row):
    return float(row["x"])+float(row["w"])*.5,float(row["y"])+float(row["h"])*.5


def nearest_duplicate_pairs(buildings, signatures):
    sig={r["building_id"]:r["visual_signature"] for r in signatures}
    districts=defaultdict(list)
    for b in buildings:districts[b.get("district","")].append(b)
    pairs=set()
    for group in districts.values():
        for b in group:
            bx,by=centre(b);nearest=None
            for o in group:
                if o["id"]==b["id"]:continue
                ox,oy=centre(o);d=math.hypot(bx-ox,by-oy)
                if nearest is None or d<nearest[0]:nearest=(d,o)
            if nearest and sig.get(b["id"])==sig.get(nearest[1]["id"]):
                pairs.add(tuple(sorted((b["id"],nearest[1]["id"]))))
    return sorted(pairs)


def pct(value):
    return f"{value:.4f}"


def metric(name,value,target,status,notes=""):
    return {"metric":name,"value":str(value),"target":str(target),"status":status,"notes":notes}


def collect_metrics():
    sem=pass20.base.SEMANTIC
    buildings=read_csv(sem/"iterated_buildings.csv")
    signatures=read_csv(sem/"building_module_signatures.csv")
    scales=read_csv(sem/"building_component_scale_audit.csv")
    frontage=read_csv(sem/"building_frontage_audit.csv")
    massing=read_csv(sem/"building_modular_massing.csv")
    details=read_csv(sem/"street_detail_pass23.csv")
    landmarks=read_csv(sem/"landmarks_pass24.csv")
    manifest={r["key"]:r["value"] for r in read_csv(pass20.base.OUT/"composition_manifest.csv")}

    sig_counts=Counter(r["visual_signature"] for r in signatures)
    max_sig_count=max(sig_counts.values(),default=0)
    max_sig_share=max_sig_count/max(1,len(signatures))
    duplicate_pairs=nearest_duplicate_pairs(buildings,signatures)
    scale_fail=[r for r in scales if r.get("status")!="pass"]
    ordinary_ids={b["id"] for b in buildings if b.get("building_kind")!="church_landmark"}
    ordinary_front=[r for r in frontage if r.get("building_id") in ordinary_ids]
    addressed=[r for r in ordinary_front if r.get("addressed")=="true"]
    road_safe=[r for r in frontage if r.get("safe_clearance")=="true"]
    gaps=[float(r.get("gap_after",0) or 0) for r in ordinary_front]
    gaps_sorted=sorted(gaps)
    p90=gaps_sorted[min(len(gaps_sorted)-1,max(0,int(math.ceil(len(gaps_sorted)*.90))-1))] if gaps_sorted else 0.0
    intentional=sum("intentional" in r.get("frontage_class","") for r in frontage)
    accidental=sum(r.get("status") not in {"pass","intentional_setback"} for r in frontage)
    irregular=[r for r in massing if r.get("building_kind")!="church_landmark" and r.get("shape_variant")!="perimeter"]
    ordinary_massing=[r for r in massing if r.get("building_kind")!="church_landmark"]
    rectangular_pct=1-len(irregular)/max(1,len(ordinary_massing))
    roof_variety=len({r.get("roof_family","") for r in signatures})
    detail_kinds=len({r.get("kind","") for r in details})
    bridge_towers=sum(r.get("kind")=="bridge_tower" for r in landmarks)
    landmark_groups=len(landmarks)-1 if bridge_towers==2 else len(landmarks)

    rows=[
        metric("building_count",len(buildings),95,"pass" if len(buildings)==95 else "fail"),
        metric("unique_visual_signatures",len(sig_counts),">=80","pass" if len(sig_counts)>=80 else "fail"),
        metric("most_used_signature_share",pct(max_sig_share),"<=0.10","pass" if max_sig_share<=.10 else "fail"),
        metric("nearest_neighbor_duplicate_pairs",len(duplicate_pairs),"<=3","pass" if len(duplicate_pairs)<=3 else "fail"),
        metric("component_scale_failures",len(scale_fail),0,"pass" if not scale_fail else "fail"),
        metric("ordinary_frontage_addressed_share",pct(len(addressed)/max(1,len(ordinary_front))),">=0.80","pass" if len(addressed)/max(1,len(ordinary_front))>=.80 else "fail"),
        metric("road_safe_buildings",len(road_safe),len(buildings),"pass" if len(road_safe)==len(buildings) else "fail"),
        metric("sidewalk_gap_min",round(min(gaps),2) if gaps else 0,"report","pass"),
        metric("sidewalk_gap_median",round(statistics.median(gaps),2) if gaps else 0,"report","pass"),
        metric("sidewalk_gap_p90",round(p90,2),"report","pass"),
        metric("sidewalk_gap_max",round(max(gaps),2) if gaps else 0,"report","pass"),
        metric("intentional_setback_rows",intentional,"report","pass"),
        metric("accidental_frontage_failures",accidental,0,"pass" if accidental==0 else "fail"),
        metric("irregular_ordinary_massing_count",len(irregular),">=65","pass" if len(irregular)>=65 else "fail"),
        metric("rectangular_ordinary_massing_share",pct(rectangular_pct),"<=0.28","pass" if rectangular_pct<=.28 else "fail"),
        metric("roof_family_variety",roof_variety,">=6","pass" if roof_variety>=6 else "fail"),
        metric("street_detail_rows",len(details),">=180","pass" if len(details)>=180 else "fail"),
        metric("street_detail_kind_count",detail_kinds,">=12","pass" if detail_kinds>=12 else "fail"),
        metric("recognizable_landmark_groups",landmark_groups,"8..12","pass" if 8<=landmark_groups<=12 else "fail"),
        metric("water_non_bridge_violations",manifest.get("non_bridge_hudson_violations","missing"),0,"pass" if manifest.get("non_bridge_hudson_violations")=="0" else "fail"),
        metric("road_segments",manifest.get("road_segments","missing"),157,"pass" if manifest.get("road_segments")=="157" else "fail"),
        metric("angled_road_segments",manifest.get("angled_road_segments","missing"),96,"pass" if manifest.get("angled_road_segments")=="96" else "fail"),
        metric("t_junctions",manifest.get("t_junctions","missing"),23,"pass" if manifest.get("t_junctions")=="23" else "fail"),
        metric("crossings",manifest.get("compact_approach_crossings","missing"),242,"pass" if manifest.get("compact_approach_crossings")=="242" else "fail"),
        metric("church_landmark_variants",manifest.get("church_landmark_count","missing"),3,"pass" if manifest.get("church_landmark_count")=="3" else "fail"),
        metric("single_map_visual_candidate",1,1,"pass","Pass 25 audits the sole Fort Lee-GWB-Washington Heights world candidate"),
    ]
    write_metrics(rows)
    return rows,buildings,landmarks


def crop_center(im,cx,cy,width=1200,height=700):
    left=max(0,min(im.width-width,int(round(cx-width/2))))
    top=max(0,min(im.height-height,int(round(cy-height/2))))
    return im.crop((left,top,left+width,top+height))


def world_master(x,y):
    return float(x)*.5,(float(y)-2048.0)*.5


def make_screenshot_suite(buildings,landmarks):
    SCREENSHOT_DIR.mkdir(parents=True,exist_ok=True)
    day=Image.open(pass20.base.OUT/"unified_composition_day.png").convert("RGB")
    night=Image.open(pass20.base.OUT/"unified_composition_night.png").convert("RGB")
    day.save(SCREENSHOT_DIR/"01_whole_day.png")
    night.save(SCREENSHOT_DIR/"02_whole_night.png")

    targets=[
        ("03_fort_lee_gwb_intersection.png",2304,6144),
        ("04_gwb_approach_and_deck.png",7550,6144),
        ("05_washington_heights_dense.png",13824,6144),
        ("06_broadway_181st.png",12160,4672),
        ("07_park_water_edge.png",4700,7900),
    ]
    church=next((r for r in landmarks if r.get("kind")=="church"),None)
    if church:
        targets.append(("08_church_landmark.png",float(church["x"])+float(church["w"])*.5,float(church["y"])+float(church["h"])*.5))
    roof=next((r for r in landmarks if r.get("visual_role")=="fort_lee_bluff_transition"),None)
    if roof:
        targets.append(("09_rooftop_detail.png",float(roof["x"])+float(roof["w"])*.5,float(roof["y"])+float(roof["h"])*.5))
    for name,wx,wy in targets:
        mx,my=world_master(wx,wy)
        crop_center(day,mx,my).save(SCREENSHOT_DIR/name)


def update_manifest(masters,metric_rows):
    path=pass20.base.OUT/"composition_manifest.csv";rows=pass20.base.read_csv(path)
    remove={"pass_id","final_visual_convergence_pass","visual_convergence_metric_count","visual_convergence_failures","fixed_screenshot_suite"}
    rows=[r for r in rows if r.get("key") not in remove and not r.get("key","").startswith("sha256_unified_composition_")]
    failures=sum(r["status"]!="pass" for r in metric_rows)
    rows.extend([
        {"key":"pass_id","value":PASS_ID},
        {"key":"final_visual_convergence_pass","value":"true"},
        {"key":"visual_convergence_metric_count","value":str(len(metric_rows))},
        {"key":"visual_convergence_failures","value":str(failures)},
        {"key":"fixed_screenshot_suite","value":"qa/pass25_screenshots"},
    ])
    for master in masters:rows.append({"key":f"sha256_{master.stem}","value":pass20.base.sha256(master)})
    pass20.base.write_csv(path,("key","value"),rows)


def main():
    pass24.PASS_ID=PASS_ID
    pass24.main()
    metric_rows,buildings,landmarks=collect_metrics()
    make_screenshot_suite(buildings,landmarks)
    masters=[pass20.base.OUT/"unified_composition_day.png",pass20.base.OUT/"unified_composition_night.png"]
    update_manifest(masters,metric_rows)
    failures=[r for r in metric_rows if r["status"]!="pass"]
    print(f"PASS25_VISUAL_CONVERGENCE metrics={len(metric_rows)} failures={len(failures)} screenshots={len(list(SCREENSHOT_DIR.glob('*.png')))}")


if __name__=="__main__":main()
