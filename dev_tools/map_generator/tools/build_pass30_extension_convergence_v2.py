from __future__ import annotations

"""Low-memory Pass-30 entrypoint.

Pass 30's first implementation allocated a full 16k x 8k temporary mask for each
night-mode transition building. That is unnecessary: painting the same white
footprint into the already-authoritative solid mask twice is idempotent. Override
only that helper and retain the complete Pass-30 art/semantic contract.
"""

import sys
from pathlib import Path

from PIL import ImageDraw

HERE=Path(__file__).resolve().parent
if str(HERE) not in sys.path:sys.path.insert(0,str(HERE))

import build_pass29_double_world as p29
import build_pass30_extension_convergence as p30


def add_transition_art_and_masks_fast(day,night,solid,walk,cycle,collision,transition):
    sd=ImageDraw.Draw(solid);cd=ImageDraw.Draw(collision);wd=ImageDraw.Draw(walk);cyd=ImageDraw.Draw(cycle)
    dayd=ImageDraw.Draw(day);nightd=ImageDraw.Draw(night)
    for row in transition:
        x=int(float(row["x"]));y=int(float(row["y"]));w=int(float(row["w"]));h=int(float(row["h"]));bid=row["building_id"]
        p29.draw_building(day,dayd,(x,y,w,h),bid,row["kind"],False,solid)
        p29.draw_building(night,nightd,(x,y,w,h),bid,row["kind"],True,solid)
        poly=p30.shape_polygon(row)
        sd.polygon(poly,fill=255);cd.polygon(poly,fill=255);wd.polygon(poly,fill=0);cyd.polygon(poly,fill=0)


def main():
    p30.add_transition_art_and_masks=add_transition_art_and_masks_fast
    p30.main()


if __name__=="__main__":main()
