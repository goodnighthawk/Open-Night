from __future__ import annotations

"""Pass 22b: visual massing convergence for the modular-building system.

Pass 22 proved component scale and module diversity, but the legacy atlas core can
still read as a small object centered inside a larger legal collision footprint.
This refinement fills the accepted footprint with deterministic L/U/stepped/
courtyard modular roof massing while preserving the detailed atlas core unchanged.
No sprite is stretched and no visual massing may leave the parent footprint.
"""

import hashlib
import sys
from collections import Counter
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import build_pass20_streetwall as pass20
import build_pass22_modular_buildings as pass22

PASS_ID = "pass_22b_modular_massing_convergence_rc1"
MASSING_CSV = "building_modular_massing.csv"
massing_rows: list[dict[str, object]] = []


def seed(text: str) -> int:
    return int(hashlib.sha256(str(text).encode("utf-8")).hexdigest()[:10], 16)


def shape_for(building, index):
    if building.get("building_kind") == "church_landmark":
        return ("cruciform_church", "parish_courtyard", "stepped_basilica")[index % 3]
    variants = ("perimeter", "l_shape", "u_shape", "stepped", "courtyard", "chamfered")
    return variants[seed(building["id"]) % len(variants)]


def polygon_area(poly):
    return abs(sum(x1*y2-x2*y1 for (x1,y1),(x2,y2) in zip(poly,poly[1:]+poly[:1]))) * .5


def shape_polygons(building, shape):
    x=float(building["x"]);y=float(building["y"]);w=float(building["w"]);h=float(building["h"])
    inset=min(18.0,max(10.0,min(w,h)*.025))
    x0=x+inset;y0=y+inset;x1=x+w-inset;y1=y+h-inset
    W=x1-x0;H=y1-y0
    polys=[];holes=[]
    if shape == "perimeter":
        polys=[[(x0,y0),(x1,y0),(x1,y1),(x0,y1)]]
    elif shape == "l_shape":
        polys=[[(x0,y0),(x1,y0),(x1,y0+H*.46),(x0+W*.48,y0+H*.46),(x0+W*.48,y1),(x0,y1)]]
    elif shape == "u_shape":
        polys=[[(x0,y0),(x1,y0),(x1,y1),(x0+W*.68,y1),(x0+W*.68,y0+H*.52),(x0+W*.32,y0+H*.52),(x0+W*.32,y1),(x0,y1)]]
    elif shape == "stepped":
        polys=[[(x0,y0),(x1-W*.20,y0),(x1-W*.20,y0+H*.18),(x1,y0+H*.18),(x1,y1),(x0,y1)]]
    elif shape == "courtyard":
        polys=[[(x0,y0),(x1,y0),(x1,y1),(x0,y1)]]
        holes=[[(x0+W*.30,y0+H*.30),(x0+W*.70,y0+H*.30),(x0+W*.70,y0+H*.70),(x0+W*.30,y0+H*.70)]]
    elif shape == "chamfered":
        c=min(W,H)*.14
        polys=[[(x0+c,y0),(x1-c,y0),(x1,y0+c),(x1,y1-c),(x1-c,y1),(x0+c,y1),(x0,y1-c),(x0,y0+c)]]
    elif shape == "cruciform_church":
        polys=[[(x0+W*.30,y0),(x0+W*.70,y0),(x0+W*.70,y0+H*.34),(x1,y0+H*.34),(x1,y0+H*.58),(x0+W*.70,y0+H*.58),(x0+W*.70,y1),(x0+W*.30,y1),(x0+W*.30,y0+H*.58),(x0,y0+H*.58),(x0,y0+H*.34),(x0+W*.30,y0+H*.34)]]
    elif shape == "parish_courtyard":
        polys=[[(x0,y0),(x1,y0),(x1,y1),(x0,y1)]]
        holes=[[(x0+W*.38,y0+H*.34),(x0+W*.72,y0+H*.34),(x0+W*.72,y0+H*.66),(x0+W*.38,y0+H*.66)]]
    else:  # stepped_basilica
        polys=[[(x0+W*.18,y0),(x1-W*.18,y0),(x1-W*.18,y0+H*.20),(x1,y0+H*.20),(x1,y1),(x0,y1),(x0,y0+H*.20),(x0+W*.18,y0+H*.20)]]
    return polys,holes


def build_massing_rows(buildings):
    massing_rows.clear();church_index=0
    for b in buildings:
        shape=shape_for(b,church_index)
        if b.get("building_kind") == "church_landmark":church_index+=1
        polys,holes=shape_polygons(b,shape)
        outer=sum(polygon_area(p) for p in polys);hole=sum(polygon_area(p) for p in holes)
        footprint=float(b["w"])*float(b["h"])
        core_w=float(b.get("cosmetic_source_bbox_w",0) or 0)*float(b.get("cosmetic_world_units_per_pixel",2) or 2)*float(b.get("cosmetic_render_scale_ratio",1) or 1)
        core_h=float(b.get("cosmetic_source_bbox_h",0) or 0)*float(b.get("cosmetic_world_units_per_pixel",2) or 2)*float(b.get("cosmetic_render_scale_ratio",1) or 1)
        massing_rows.append({
            "building_id":b["id"],"district":b.get("district",""),"building_kind":b.get("building_kind",""),
            "shape_variant":shape,"footprint_fill_ratio":round(max(0,min(1,(outer-hole)/max(1,footprint))),4),
            "core_visual_w":round(core_w,2),"core_visual_h":round(core_h,2),
            "footprint_w":b["w"],"footprint_h":b["h"],"scale_mode":"fixed_component_modular_extension_v1",
        })
    pass20.base.write_csv(pass20.base.SEMANTIC/MASSING_CSV,
        ("building_id","district","building_kind","shape_variant","footprint_fill_ratio","core_visual_w","core_visual_h","footprint_w","footprint_h","scale_mode"),massing_rows)


def to_master(poly):
    return [tuple(map(lambda v:int(round(v)),pass20.base.world_to_master(x,y))) for x,y in poly]


def draw_massing(path:Path,buildings,night:bool):
    im=Image.open(path).convert("RGBA")
    overlay=Image.new("RGBA",im.size,(0,0,0,0));d=ImageDraw.Draw(overlay,"RGBA")
    by_id={r["building_id"]:r for r in massing_rows}
    for b in buildings:
        shape=by_id[b["id"]]["shape_variant"];polys,holes=shape_polygons(b,shape)
        s=seed(b["id"])
        if night:
            roof_options=((42,44,42,215),(48,46,41,215),(38,45,46,215),(53,48,42,215));edge=(102,103,96,230);seam=(29,31,30,135)
        else:
            roof_options=((94,91,81,210),(105,99,86,210),(84,96,96,210),(112,101,84,210));edge=(145,139,122,230);seam=(66,67,62,120)
        roof=roof_options[s%len(roof_options)]
        for poly in polys:
            pts=to_master(poly);d.polygon(pts,fill=roof,outline=edge)
            xs=[p[0] for p in pts];ys=[p[1] for p in pts]
            # restrained roof seams at fixed visual pitch
            for xx in range(min(xs)+18,max(xs),34):d.line((xx,min(ys),xx,max(ys)),fill=seam,width=1)
        for hole in holes:
            d.polygon(to_master(hole),fill=(0,0,0,0))

        # Preserve the detailed approved atlas core exactly: remove its centered
        # visual rectangle from the extension overlay before compositing.
        core_w=float(b.get("cosmetic_source_bbox_w",0) or 0)*float(b.get("cosmetic_world_units_per_pixel",2) or 2)*float(b.get("cosmetic_render_scale_ratio",1) or 1)
        core_h=float(b.get("cosmetic_source_bbox_h",0) or 0)*float(b.get("cosmetic_world_units_per_pixel",2) or 2)*float(b.get("cosmetic_render_scale_ratio",1) or 1)
        cx=float(b["x"])+float(b["w"])*.5;cy=float(b["y"])+float(b["h"])*.5
        a=pass20.base.world_to_master(cx-core_w*.5,cy-core_h*.5);c=pass20.base.world_to_master(cx+core_w*.5,cy+core_h*.5)
        d.rectangle((int(a[0]),int(a[1]),int(c[0]),int(c[1])),fill=(0,0,0,0))
    Image.alpha_composite(im,overlay).convert("RGB").save(path)


def update_manifest(masters):
    path=pass20.base.OUT/"composition_manifest.csv";rows=pass20.base.read_csv(path)
    remove={"pass_id","modular_massing_convergence_pass","modular_massing_shapes","irregular_massing_share","church_massing_variants"}
    rows=[r for r in rows if r.get("key") not in remove and not r.get("key","").startswith("sha256_unified_composition_")]
    counts=Counter(r["shape_variant"] for r in massing_rows)
    irregular=sum(r["shape_variant"]!="perimeter" for r in massing_rows)/max(1,len(massing_rows))
    church=len({r["shape_variant"] for r in massing_rows if r["building_kind"]=="church_landmark"})
    rows.extend([
        {"key":"pass_id","value":PASS_ID},
        {"key":"modular_massing_convergence_pass","value":"true"},
        {"key":"modular_massing_shapes","value":str(len(counts))},
        {"key":"irregular_massing_share","value":f"{irregular:.4f}"},
        {"key":"church_massing_variants","value":str(church)},
    ])
    for master in masters:rows.append({"key":f"sha256_{master.stem}","value":pass20.base.sha256(master)})
    pass20.base.write_csv(path,("key","value"),rows)


def main():
    if MASSING_CSV not in pass20.base.SEMANTIC_FILES:
        pass20.base.SEMANTIC_FILES=tuple(pass20.base.SEMANTIC_FILES)+(MASSING_CSV,)
    pass22.PASS_ID=PASS_ID
    real_draw=pass22.draw_module_layer
    pass22.draw_module_layer=lambda path,night:None
    try:
        pass22.main()
    finally:
        pass22.draw_module_layer=real_draw
    buildings=pass20.base.read_csv(pass20.base.SEMANTIC/"iterated_buildings.csv")
    build_massing_rows(buildings)
    masters=[pass20.base.OUT/"unified_composition_day.png",pass20.base.OUT/"unified_composition_night.png"]
    draw_massing(masters[0],buildings,False);draw_massing(masters[1],buildings,True)
    real_draw(masters[0],False);real_draw(masters[1],True)
    pass20.base.tile_masters(masters);update_manifest(masters)
    counts=Counter(r["shape_variant"] for r in massing_rows)
    print(f"PASS22B_MASSING buildings={len(buildings)} shapes={dict(sorted(counts.items()))}")


if __name__=="__main__":main()
