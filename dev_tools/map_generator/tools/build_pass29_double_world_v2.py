from __future__ import annotations

"""Low-memory Pass-29 entrypoint.

The protected Pass-28 core is pasted after extension rendering, so extension roads
can be drawn directly without allocating a full 16k x 8k clipping layer per road.
This keeps the doubled-world release candidate practical on CI while preserving
exactly the same output contract as build_pass29_double_world.py.
"""

import math
import sys
from pathlib import Path

from PIL import ImageDraw

HERE=Path(__file__).resolve().parent
if str(HERE) not in sys.path:sys.path.insert(0,str(HERE))

import build_pass29_double_world as p29


def draw_roads_fast(im,roads,night,walkable,roadmask):
    P=p29.palette(night);d=ImageDraw.Draw(im);wd=ImageDraw.Draw(walkable);rd=ImageDraw.Draw(roadmask)
    for row in roads:
        asphalt,sidewalk,curb=p29.road_style(row);pts=row["points"]
        p29.draw_polyline(d,pts,P["sidewalk"],asphalt+2*(sidewalk+curb))
        p29.draw_polyline(d,pts,P["curb"],asphalt+2*curb)
        p29.draw_polyline(d,pts,P["road"],asphalt)
        p29.draw_polyline(rd,pts,255,asphalt+2*(sidewalk+curb))
        p29.draw_polyline(wd,pts,255,asphalt+2*(sidewalk+curb))
        if int(row["lanes"])>=2:
            for a,b in zip(pts,pts[1:]):
                dx=b[0]-a[0];dy=b[1]-a[1];length=math.hypot(dx,dy)
                if length<1:continue
                ux,uy=dx/length,dy/length;q=0.0
                while q<length:
                    q2=min(length,q+12.0)
                    d.line((a[0]+ux*q,a[1]+uy*q,a[0]+ux*q2,a[1]+uy*q2),fill=P["lane"],width=2)
                    q+=34.0


def main():
    p29.draw_roads=draw_roads_fast
    p29.main()


if __name__=="__main__":main()
