from __future__ import annotations

import csv
import zipfile
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from mapfiles.loader import load_map_folder, validate_map
import versioning

MAP_DIRS=(
    ROOT/"mapfiles"/"data"/"map_001_gwb_corridor",
    ROOT/"dev_tools"/"map_generator"/"mapfiles"/"data"/"map_001_gwb_corridor",
)
ARCHIVE=ROOT/"assets"/"environment"/"approved"/"map_001_gwb_corridor"/"composition_tiles_v25.zip"


def table(path):
    with Path(path).open("r",encoding="utf-8-sig",newline="") as f:return list(csv.DictReader(f))


def kv(path):return {r["key"]:r["value"] for r in table(path)}


def main():
    problems=[]
    if versioning.GAME_VERSION!="0.8.2":problems.append(f"wire version is {versioning.GAME_VERSION}, expected 0.8.2")
    if "v0.8.2" not in (ROOT/"VERSION.txt").read_text(encoding="utf-8"):problems.append("VERSION.txt is not v0.8.2")
    if not ARCHIVE.is_file():problems.append("Pass 25 baked archive missing")
    else:
        with zipfile.ZipFile(ARCHIVE,"r") as z:
            pngs=[n for n in z.namelist() if n.endswith(".png")]
            days=[n for n in pngs if n.startswith("day/")];nights=[n for n in pngs if n.startswith("night/")]
            if len(pngs)!=64 or len(days)!=32 or len(nights)!=32:problems.append(f"archive tiles day/night/total={len(days)}/{len(nights)}/{len(pngs)}, expected 32/32/64")
    for folder in MAP_DIRS:
        if not folder.is_dir():problems.append(f"runtime map folder missing: {folder}");continue
        m=kv(folder/"map.csv");r=kv(folder/"render_contract.csv")
        expected={
            "id":"map_001_gwb_corridor",
            "baked_composition_archive":"assets/environment/approved/map_001_gwb_corridor/composition_tiles_v25.zip",
            "map_build_id":"open_night_v0_8_2_pass25_default_only",
            "render_pass":"25",
            "building_sprite_scale_band":"0.88..1.12",
            "final_visual_convergence_pass":"true",
            "visual_convergence_failures":"0",
        }
        for key,value in expected.items():
            if m.get(key)!=value:problems.append(f"{folder.name}: map.csv {key}={m.get(key)!r}, expected {value!r}")
        if r.get("render_pass")!="25":problems.append(f"{folder.name}: render_contract pass is not 25")
        for required in ("building_modules.csv","building_module_signatures.csv","building_modular_massing.csv","street_detail_pass23.csv","landmarks_pass24.csv","building_component_scale_audit.csv","building_frontage_audit.csv"):
            if not (folder/required).is_file():problems.append(f"{folder.name}: missing {required}")
        cfg=load_map_folder(folder,attach_grid=False)
        errors=validate_map(cfg)
        if errors:problems.append(f"{folder.name}: runtime validation has {len(errors)} errors; first={errors[0]}")
        if len(cfg.get("roads",[]))!=38:problems.append(f"{folder.name}: expected 38 roads")
        if len(cfg.get("buildings",[]))!=95:problems.append(f"{folder.name}: expected 95 buildings")
        if len(cfg.get("crosswalks",[]))!=242:problems.append(f"{folder.name}: expected 242 crossings, got {len(cfg.get('crosswalks',[]))}")
        if len(cfg.get("landmarks",[]))<15:problems.append(f"{folder.name}: Pass 24 landmarks were not promoted")
    print(f"PASS25_RUNTIME_PROMOTION_AUDIT maps={len(MAP_DIRS)} problems={len(problems)} archive={ARCHIVE.name}")
    if problems:
        print("PASS25_RUNTIME_PROMOTION_GATE=FAIL")
        for p in problems[:30]:print(" - "+p)
        return 1
    print("PASS25_RUNTIME_PROMOTION_GATE=PASS")
    return 0

if __name__=="__main__":raise SystemExit(main())
