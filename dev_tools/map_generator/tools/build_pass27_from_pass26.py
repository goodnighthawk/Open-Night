from __future__ import annotations

"""Apply Pass 27 to an already-built and audited Pass 26 RC4 output."""

import sys
from pathlib import Path

from PIL import Image, ImageDraw

HERE=Path(__file__).resolve().parent
if str(HERE) not in sys.path:sys.path.insert(0,str(HERE))

import build_pass27_intentional_open_blocks as pass27


def draw_open_blocks_fixed(output_path:Path, rows, night:bool):
    """Pass-27 renderer with the output path kept distinct from path paint color."""
    im=Image.open(output_path).convert("RGB");d=ImageDraw.Draw(im,"RGB")
    if night:
        curb=(78,79,74);grass=(47,66,48);grass2=(57,76,53);path_color=(84,82,74);asphalt=(52,55,54);stripe=(142,137,118);tree=(45,76,51);tree2=(63,91,58);car=(81,83,79);lamp=(196,156,86)
    else:
        curb=(121,119,108);grass=(79,107,73);grass2=(91,119,80);path_color=(142,137,123);asphalt=(78,82,80);stripe=(205,198,170);tree=(52,91,58);tree2=(76,112,69);car=(117,119,112);lamp=(224,184,104)
    for row in rows:
        (x,y,w,h),features=pass27.block_features(row);box=(x,y,x+w,y+h)
        d.rectangle((x-3,y-3,x+w+3,y+h+3),fill=curb)
        if row["use"]=="green_space":
            d.rectangle(box,fill=grass)
            for yy in range(y+8,y+h-6,16):
                d.line((x+3,yy,x+w-3,yy),fill=grass2,width=1)
            for kind,geom in features:
                if kind=="cycle_path":d.rectangle(geom,fill=path_color)
            for off in (-36,36):
                bx=x+w//2+off;by=y+h//2+22
                d.rectangle((bx-8,by-2,bx+8,by+2),fill=curb)
            for lx,ly in ((x+14,y+14),(x+w-14,y+14),(x+14,y+h-14),(x+w-14,y+h-14)):
                d.ellipse((lx-3,ly-3,lx+3,ly+3),fill=lamp)
            for kind,geom in features:
                if kind=="tree":
                    tx,ty,r=geom
                    d.ellipse((tx-r-2,ty-r-1,tx+r+2,ty+r+3),fill=(39,53,40))
                    d.ellipse((tx-r,ty-r,tx+r,ty+r),fill=tree)
                    d.ellipse((tx-r+1,ty-r+1,tx+r-2,ty+r-2),fill=tree2)
        else:
            d.rectangle(box,fill=asphalt)
            horizontal=w>=h
            if horizontal:
                mid=y+h//2
                d.rectangle((x+5,mid-14,x+w-5,mid+14),fill=(65,68,66) if not night else (45,48,47))
                for xx in range(x+10,x+w-8,28):
                    d.line((xx,y+5,xx,mid-17),fill=stripe,width=1)
                    d.line((xx,mid+17,xx,y+h-5),fill=stripe,width=1)
            else:
                mid=x+w//2
                d.rectangle((mid-14,y+5,mid+14,y+h-5),fill=(65,68,66) if not night else (45,48,47))
                for yy in range(y+10,y+h-8,28):
                    d.line((x+5,yy,mid-17,yy),fill=stripe,width=1)
                    d.line((mid+17,yy,x+w-5,yy),fill=stripe,width=1)
            for kind,geom in features:
                if kind=="parked_car":
                    x0,y0,x1,y1=geom
                    d.rectangle((x0+2,y0+2,x1+2,y1+2),fill=(35,37,36))
                    d.rectangle(geom,fill=car,outline=curb,width=1)
            for lx,ly in ((x+12,y+12),(x+w-12,y+12),(x+12,y+h-12),(x+w-12,y+h-12)):
                d.ellipse((lx-2,ly-2,lx+2,ly+2),fill=lamp)
    im.save(output_path)


def main():
    # The release-candidate workflow builds and audits RC4 first. Avoid rebuilding
    # it a second time; all remaining Pass-27 stages consume that protected output.
    pass27.rc4.main=lambda:None
    pass27.draw_open_blocks=draw_open_blocks_fixed
    pass27.main()


if __name__=="__main__":main()
