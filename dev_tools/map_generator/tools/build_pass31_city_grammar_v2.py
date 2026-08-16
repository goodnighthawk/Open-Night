from __future__ import annotations

"""Low-memory Pass-31 entrypoint.

Use the already-authoritative solid mask for both day and night building painting;
painting the same footprint twice is idempotent and avoids allocating a 16k x 8k
temporary mask for every transition building.
"""

import sys
from pathlib import Path
from PIL import ImageDraw

HERE=Path(__file__).resolve().parent
if str(HERE) not in sys.path:sys.path.insert(0,str(HERE))

import build_pass31_city_grammar as p31
import city_art_grammar as grammar


def add_transition_art_and_masks_fast(day,night,solid,walk,cycle,collision,transition):
    sd=ImageDraw.Draw(solid);cd=ImageDraw.Draw(collision);wd=ImageDraw.Draw(walk);cyd=ImageDraw.Draw(cycle)
    dayd=ImageDraw.Draw(day);nightd=ImageDraw.Draw(night)
    for row in transition:
        x=int(float(row["x"]));y=int(float(row["y"]));w=int(float(row["w"]));h=int(float(row["h"]));bid=row["building_id"]
        p31.draw_building_grammar(day,dayd,(x,y,w,h),bid,row["kind"],False,solid)
        p31.draw_building_grammar(night,nightd,(x,y,w,h),bid,row["kind"],True,solid)
        merged=int(float(row.get("merged_lot_count",1) or 1));variant=grammar.massing_variant(bid,merged)
        for poly in p31.shape_polygons(x,y,w,h,variant):
            sd.polygon(poly,fill=255);cd.polygon(poly,fill=255);wd.polygon(poly,fill=0);cyd.polygon(poly,fill=0)


def main():
    p31.add_transition_art_and_masks_grammar=add_transition_art_and_masks_fast
    p31.main()


if __name__=="__main__":main()
