from __future__ import annotations
from pathlib import Path
import math,sys
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from common import get_map,world_to_chunk,world_to_region,region_label
cfg=get_map('map_001_gwb_corridor');errors=[]
cols=int(cfg.get('chunk_cols',0));rows=int(cfg.get('chunk_rows',0));cs=int(cfg.get('chunk_size',0));ww=int(cfg.get('world_w',0));wh=int(cfg.get('world_h',0));area=int(cfg.get('map_area_multiplier',0))
# Pass 9 may rigidly rotate the full map and reshape 24x8 -> 16x12 while preserving
# the exact 192-chunk / 2x-area scalability contract. Shape is no longer fixed.
if cols*rows!=192:errors.append(f'expected 192 chunks after rigid map rotation, got {cols}x{rows}={cols*rows}')
if (ww,wh)!=(cols*cs,rows*cs):errors.append(f'world dimensions {(ww,wh)} do not match chunk grid {cols}x{rows} @ {cs}')
if area!=2:errors.append(f'map_area_multiplier must remain 2, got {area}')
if cs!=1024:errors.append('chunk_size must remain 1024')
rc=int(cfg.get('server_region_chunk_cols',8));rr=int(cfg.get('server_region_chunk_rows',4))
if (rc,rr)!=(8,4):errors.append(f'server region span must remain 8x4 chunks, got {rc}x{rr}')
regions={world_to_region((cx+.5)*cs,(cy+.5)*cs,cfg) for cy in range(rows) for cx in range(cols)}
expected_regions=math.ceil(cols/rc)*math.ceil(rows/rr)
if len(regions)!=expected_regions:errors.append(f'expected {expected_regions} logical regions, got {len(regions)}')
checks=[(0,0),(ww-1,wh-1),(ww*.5,wh*.5)]
for x,y in checks:
    ch=world_to_chunk(x,y,cfg); exp=(min(cols-1,max(0,int(x//cs))),min(rows-1,max(0,int(y//cs))))
    if ch!=exp:errors.append(f'{(x,y)}: wrong chunk {ch} != {exp}')
    rg=world_to_region(x,y,cfg)
    if rg not in regions:errors.append(f'{(x,y)}: invalid region {rg}/{region_label(*rg)}')
radius=int(cfg.get('interest_radius_chunks',2));max_interest=(radius*2+1)**2
if max_interest!=25:errors.append(f'expected 25-chunk max interest window, got {max_interest}')
if errors:
    print('SPATIAL INTEREST AUDIT: FAIL')
    for e in errors:print(' -',e)
    raise SystemExit(1)
print('SPATIAL INTEREST AUDIT: PASS')
print(f' map: {cols}x{rows} chunks / {cols*rows} total = {area}x prior area')
print(f' regions: {math.ceil(cols/rc)}x{math.ceil(rows/rr)} = {len(regions)} logical server regions, {rc}x{rr} chunks each')
print(f' per-player network interest: radius {radius} -> at most {max_interest} chunk buckets')
