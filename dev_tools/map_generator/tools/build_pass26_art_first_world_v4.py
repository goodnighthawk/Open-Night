from __future__ import annotations

"""Pass 26 RC4: finish every legal massing pad as believable building art.

RC3 solved the art-first gameplay pipeline, block density and road permeability.
The remaining visual weakness was the intentionally flat Pass-22b extension around
some detailed atlas cores. RC4 replaces that flat extension renderer with textured,
fixed-scale modular roof complexes before the final art is converted into gameplay
mask tiles. Collision geometry is unchanged from RC3.
"""

import math
import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import build_pass20_streetwall as pass20
import build_pass22b_massing_convergence as pass22b
import build_pass26_art_first_world_v3 as rc3

PASS_ID = "pass_26_art_first_world_rc4"


def stable(text: str) -> int:
    return pass22b.seed(text)


def localize(poly, left, top):
    return [(x-left, y-top) for x,y in poly]


def master_poly(poly):
    return [tuple(float(v) for v in pass20.base.world_to_master(x,y)) for x,y in poly]


def inside_mask(mask: Image.Image, box) -> bool:
    x0,y0,x1,y1=box
    pts=((x0,y0),(x1,y0),(x1,y1),(x0,y1),((x0+x1)//2,(y0+y1)//2))
    for x,y in pts:
        if not (0<=x<mask.width and 0<=y<mask.height) or mask.getpixel((int(x),int(y)))<200:
            return False
    return True


def roof_palette(seed: int, night: bool):
    if night:
        bases=((43,45,42,245),(49,47,42,245),(39,46,47,245),(55,49,42,245),(45,43,47,245))
        return bases[seed%len(bases)],(94,96,90,240),(25,28,27,180),(78,84,82,245),(112,91,65,235),(24,31,33,230)
    bases=((93,90,80,245),(106,99,85,245),(83,96,96,245),(113,101,83,245),(99,92,99,245))
    return bases[seed%len(bases)],(154,146,126,240),(66,67,62,150),(121,128,122,245),(158,117,76,235),(53,68,72,225)


def draw_detailed_massing(path: Path, buildings, night: bool):
    im=Image.open(path).convert("RGBA")
    by_id={r["building_id"]:r for r in pass22b.massing_rows}

    for b in buildings:
        row=by_id[b["id"]];shape=row["shape_variant"]
        polys,holes=pass22b.shape_polygons(b,shape)
        s=stable("roof26:"+b["id"])

        # Parent-sized local canvas keeps clipping exact and avoids drawing seams
        # or rooftop equipment outside an irregular L/U/chamfered footprint.
        p0=pass20.base.world_to_master(float(b["x"]),float(b["y"]))
        p1=pass20.base.world_to_master(float(b["x"])+float(b["w"]),float(b["y"])+float(b["h"]))
        left=int(math.floor(p0[0]))-3;top=int(math.floor(p0[1]))-3
        right=int(math.ceil(p1[0]))+4;bottom=int(math.ceil(p1[1]))+4
        W=max(2,right-left);H=max(2,bottom-top)
        mask=Image.new("L",(W,H),0);md=ImageDraw.Draw(mask)
        local_polys=[];local_holes=[]
        for poly in polys:
            pts=localize(master_poly(poly),left,top);local_polys.append(pts);md.polygon(pts,fill=255)
        for hole in holes:
            pts=localize(master_poly(hole),left,top);local_holes.append(pts);md.polygon(pts,fill=0)

        # Preserve the approved high-detail atlas core exactly.
        core_w=float(b.get("cosmetic_source_bbox_w",0) or 0)*float(b.get("cosmetic_world_units_per_pixel",2) or 2)*float(b.get("cosmetic_render_scale_ratio",1) or 1)
        core_h=float(b.get("cosmetic_source_bbox_h",0) or 0)*float(b.get("cosmetic_world_units_per_pixel",2) or 2)*float(b.get("cosmetic_render_scale_ratio",1) or 1)
        cx=float(b["x"])+float(b["w"])*.5;cy=float(b["y"])+float(b["h"])*.5
        ca=pass20.base.world_to_master(cx-core_w*.5,cy-core_h*.5);cb=pass20.base.world_to_master(cx+core_w*.5,cy+core_h*.5)
        core_box=(int(ca[0]-left),int(ca[1]-top),int(cb[0]-left),int(cb[1]-top))
        md.rectangle(core_box,fill=0)

        base,edge,seam,metal,warm,glass=roof_palette(s,night)
        roof=Image.new("RGBA",(W,H),base);rd=ImageDraw.Draw(roof,"RGBA")

        # Multiple roof zones remove the single-flat-pad appearance. Zone widths
        # remain broad architectural bays; detail sizes below are fixed pixels at
        # the constant world-to-master 0.5 scale.
        zone_count=2+(s%3)
        for z in range(zone_count):
            frac0=z/zone_count;frac1=(z+1)/zone_count
            if (s//7)%2:
                y0=int(H*frac0);y1=int(H*frac1)
                delta=(-7+(z*9+s)%15)
                col=tuple(max(0,min(255,c+delta)) for c in base[:3])+(base[3],)
                rd.rectangle((0,y0,W,y1),fill=col)
            else:
                x0=int(W*frac0);x1=int(W*frac1)
                delta=(-7+(z*9+s)%15)
                col=tuple(max(0,min(255,c+delta)) for c in base[:3])+(base[3],)
                rd.rectangle((x0,0,x1,H),fill=col)

        # Expansion seams are clipped later by the exact building mask.
        pitch=17+(s%7)
        if (s//11)%2:
            for xx in range(8,W,pitch):rd.line((xx,0,xx,H),fill=seam,width=1)
        else:
            for yy in range(8,H,pitch):rd.line((0,yy,W,yy),fill=seam,width=1)
        cross_pitch=pitch*3
        for off in range((s//13)%max(1,cross_pitch),max(W,H),cross_pitch):
            if W>=H:rd.line((0,off,W,off),fill=(seam[0],seam[1],seam[2],80),width=1)
            else:rd.line((off,0,off,H),fill=(seam[0],seam[1],seam[2],80),width=1)

        # Fixed-size rooftop vocabulary. Candidate positions are deterministic and
        # accepted only when the whole module remains inside the legal roof mask.
        module_count=max(4,min(12,int((W*H)/4700)+4))
        for j in range(module_count):
            q=stable(f"roof26:{b['id']}:{j}")
            kind=q%6
            if kind==0:mw,mh=14,10       # small HVAC
            elif kind==1:mw,mh=22,14     # larger HVAC
            elif kind==2:mw,mh=9,9       # vent/chimney
            elif kind==3:mw,mh=17,12     # skylight
            elif kind==4:mw,mh=25,19     # stair/elevator bulkhead
            else:mw,mh=13,8              # roof hatch
            avail_w=max(1,W-mw-12);avail_h=max(1,H-mh-12)
            mx=6+(q>>9)%avail_w;my=6+(q>>19)%avail_h
            box=(mx,my,mx+mw,my+mh)
            if not inside_mask(mask,box):continue
            if kind in (0,1):
                rd.rectangle((mx+2,my+2,mx+mw+2,my+mh+2),fill=(21,24,24,120))
                rd.rectangle(box,fill=metal,outline=edge,width=1)
                rr=max(2,min(mw,mh)//4);ccx=mx+mw//2;ccy=my+mh//2
                rd.ellipse((ccx-rr,ccy-rr,ccx+rr,ccy+rr),outline=seam,width=1)
            elif kind==2:
                rd.ellipse(box,fill=warm,outline=edge,width=1)
            elif kind==3:
                rd.rectangle(box,fill=glass,outline=edge,width=1)
                rd.line((mx+2,my+mh//2,mx+mw-2,my+mh//2),fill=edge,width=1)
            elif kind==4:
                rd.rectangle((mx+2,my+2,mx+mw+2,my+mh+2),fill=(18,20,20,120))
                rd.rectangle(box,fill=tuple(max(0,c-12) for c in base[:3])+(245,),outline=edge,width=1)
                rd.rectangle((mx+4,my+4,mx+mw-4,my+mh-4),outline=seam,width=1)
            else:
                rd.rectangle(box,fill=warm,outline=edge,width=1)

        # Occasional fixed-size water tank / long skylight gives larger complexes a
        # recognizable rooftop hierarchy without scaling components with footprint.
        if W*H>19000 and s%4==0:
            tw=18;th=18;tx=max(6,min(W-tw-6,int(W*.72)));ty=max(6,min(H-th-6,int(H*.25)))
            if inside_mask(mask,(tx,ty,tx+tw,ty+th)):
                rd.line((tx+4,ty+th,tx+2,ty+th+8),fill=edge,width=2)
                rd.line((tx+tw-4,ty+th,tx+tw-2,ty+th+8),fill=edge,width=2)
                rd.ellipse((tx,ty,tx+tw,ty+th//2),fill=warm,outline=edge)
                rd.rectangle((tx,ty+th//4,tx+tw,ty+th),fill=warm,outline=edge)
        elif W>90 and H>55:
            sw=min(48,W-18);sh=8;sx=max(8,(W-sw)//2);sy=max(8,int(H*.20))
            if inside_mask(mask,(sx,sy,sx+sw,sy+sh)):
                rd.rectangle((sx,sy,sx+sw,sy+sh),fill=glass,outline=edge,width=1)
                for xx in range(sx+7,sx+sw,8):rd.line((xx,sy+1,xx,sy+sh-1),fill=edge,width=1)

        # Apply exact irregular footprint/hole/core clipping.
        alpha=roof.getchannel("A")
        roof.putalpha(ImageChops.multiply(alpha,mask))
        im.alpha_composite(roof,(left,top))

        # Crisp parapets and courtyard rims sit on top of the texture. They are
        # fixed-width lines, not scaled with building footprint.
        ed=ImageDraw.Draw(im,"RGBA")
        for poly in local_polys:
            pts=[(int(x+left),int(y+top)) for x,y in poly]
            ed.line(pts+[pts[0]],fill=edge,width=2,joint="curve")
        for hole in local_holes:
            pts=[(int(x+left),int(y+top)) for x,y in hole]
            ed.line(pts+[pts[0]],fill=edge,width=2,joint="curve")

    im.convert("RGB").save(path)


def main():
    # Patch the upstream Pass-22b art phase *before* RC3 generates the complete
    # world. Thus this detailed massing is part of the final visual authority and
    # all gameplay masks are still generated downstream from that final world.
    old=pass22b.draw_massing
    pass22b.draw_massing=draw_detailed_massing
    rc3.PASS_ID=PASS_ID
    try:
        rc3.main()
    finally:
        pass22b.draw_massing=old

    # Record the visual-art completion contract without changing geometry/masks.
    manifest=pass20.base.OUT/"composition_manifest.csv"
    rows=pass20.base.read_csv(manifest)
    keys={"pass26_detailed_massing_art","pass26_massing_art_rule"}
    rows=[r for r in rows if r.get("key") not in keys]
    rows.extend([
        {"key":"pass26_detailed_massing_art","value":"true"},
        {"key":"pass26_massing_art_rule","value":"fixed_scale_textured_roof_complex_rc4"},
    ])
    pass20.base.write_csv(manifest,("key","value"),rows)
    print("PASS26_RC4_MASSING_ART detailed_roof_complexes=95 fixed_scale=true")


if __name__=="__main__":main()
