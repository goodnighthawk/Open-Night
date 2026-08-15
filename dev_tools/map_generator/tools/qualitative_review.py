from __future__ import annotations
import csv,math,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from cosmetic_pack import load_catalog
MAP=ROOT/'mapfiles'/'data'/'map_001_gwb_corridor';COS=ROOT/'working_cosmetics';OUT=ROOT/'output'

def read(p):
    p=p if isinstance(p,Path) else MAP/p
    if not p.exists():return []
    with p.open('r',encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def fv(r,k,d=0):
    try:return float(r.get(k,d) or d)
    except:return float(d)

def run():
    cat=load_catalog();inst=read(COS/'cosmetic_instances.csv');signs=read(COS/'road_sign_anchors.csv');landmarks=read(COS/'landmark_anchors.csv');cables=read(COS/'bridge_cables.csv');lights=read(COS/'light_emitters.csv');massing=read(COS/'building_massing.csv');overlays=read(COS/'layout_overlays.csv');dressing=read(COS/'street_dressing.csv');build=read('buildings.csv');roads=read('roads.csv');props=read('street_props.csv')
    used={r['archetype_id'] for r in inst if r.get('archetype_id')}|{r['archetype_id'] for r in landmarks if r.get('archetype_id')};families={r['family'] for r in cat if r['archetype_id'] in used}
    bskins={r['object_id'] for r in inst if r['game_type']=='building'}
    major=[r for r in roads if (r.get('highway') or '').lower() in {'motorway','trunk','primary','secondary'}]
    ordinary=[r for r in roads if not (r.get('highway') or '').lower().startswith('motorway')]
    sidewalk_presence=sum(1 for r in ordinary if fv(r,'sidewalk_width')>0)/max(1,len(ordinary))
    sidewalk_ratio=sum(1 for r in ordinary if fv(r,'sidewalk_width')>=24)/max(1,len(ordinary))
    metrics=[
      ('Cosmetic archetype budget',len(cat),'<= 100','PASS' if len(cat)<=100 else 'FAIL','Hard cap preserves a small reusable art vocabulary.'),
      ('Gameplay buildings with cosmetic skin',len(bskins),f'{len(build)} expected','PASS' if len(bskins)>=len(build) else 'REVIEW','Every building should be skinnable without altering footprint/collision.'),
      ('Cosmetic families used',len(families),'12+','PASS' if len(families)>=12 else 'REVIEW','Enough recurring families to create district identity without asset sprawl.'),
      ('3D sign anchors',len(signs),'20–120','PASS' if 20<=len(signs)<=120 else 'REVIEW','Vertical road infrastructure should be visible but not clutter every road.'),
      ('Bespoke landmark anchors',len(landmarks),'4+','PASS' if len(landmarks)>=4 else 'REVIEW','GWB and waterfront landmarks should not fall back to generic road/building art.'),
      ('Bridge cable definitions',len(cables),'2+','PASS' if len(cables)>=2 else 'REVIEW','Suspension-cable visuals are independent cosmetic geometry over the semantic bridge deck.'),
      ('Independent light emitters',len(lights),'80–450','PASS' if 80<=len(lights)<=450 else 'REVIEW','Night mood should come from local light pools, not a single dark filter.'),
      ('Cosmetic building massing volumes',len(massing),f'>= {len(build)}','PASS' if len(massing)>=len(build) else 'REVIEW','Large semantic footprints should break into richer visual masses without changing collision.'),
      ('Authored layout overlays',len(overlays),'20+','PASS' if len(overlays)>=20 else 'REVIEW','Alleys/lightwells/cut-through cues provide memorable top-down layout structure without copying another map.'),
      ('Cosmetic street dressing',len(dressing),'150+','PASS' if len(dressing)>=150 else 'REVIEW','Dense reusable dressing improves urban richness without increasing the 100-object archetype budget.'),
      ('Walkable-road sidewalk presence',f'{sidewalk_presence*100:.1f}%','100% except motorways','PASS' if sidewalk_presence>=.999 else 'REVIEW','Every non-motorway road should provide a pedestrian edge so road-walking is rarely necessary.'),
      ('Readable wide sidewalk coverage',f'{sidewalk_ratio*100:.1f}%','>= 70%','PASS' if sidewalk_ratio>=.70 else 'REVIEW','Most ordinary streets should retain a strong bright sidewalk/curb band; narrow trunk sidewalks may be intentionally slimmer.'),
      ('Major-road count',len(major),'informational','INFO','Road hierarchy is reviewed structurally, never by pixel registration.'),
      ('Placed street props',len(props),'informational','INFO','Dense recurring props support the gritty callback atmosphere.'),
    ]
    OUT.mkdir(exist_ok=True)
    with (OUT/'qualitative_metrics.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f);w.writerow(['criterion','current','target','status','why_it_matters']);w.writerows(metrics)
    report=['# map_generator v0.4 qualitative art-direction review','',
      'This audit intentionally performs **no pixel-difference or image-registration scoring**. The supplied GTA2 screenshots and approved NYC/GWB images are art-direction references, not images the semantic map is expected to line up with.','',
      '## Current structural checks','']
    for name,current,target,status,why in metrics:report.append(f'- **{status} — {name}:** {current} (target {target}). {why}')
    report += ['', '## Visual review priorities for the next human/ChatGPT pass','',
      '1. Does the street scene read immediately at gameplay zoom: dark asphalt, light sidewalks/curbs, bold crossings and clean silhouettes?',
      '2. Do buildings form convincing urban walls rather than isolated semantic rectangles?',
      '3. Does each district feel authored through recurring facade/roof/prop families without exceeding the object budget?',
      '4. At night, are there distinct warm/cool local light pools, darker unlit areas, readable vehicles/props, and stronger sign/storefront presence?',
      '5. Are bridge/highway approaches given bespoke vertical infrastructure: gantries, signs, barriers and lights?',
      '6. Are waterfront/industrial edges dense with retaining walls, railings, docks, fences and utility clutter rather than empty land?',
      '7. Are roads adjusted for gameplay readability where literal reference tracing hurts the composition?',
      '8. Does the layout create memorable loops, cut-throughs, landmark approaches and district identity without copying GTA2 geometry?',
      '', '## Architecture contract','',
      '- Gameplay type, collision and networking remain authoritative and style-neutral.',
      '- `cosmetic_instances.csv` maps stable game object IDs to reusable cosmetic archetypes.',
      '- `road_sign_anchors.csv` is a derived 2.5D cosmetic structure layer.',
      '- `landmark_anchors.csv` and `bridge_cables.csv` provide replaceable GWB/lighthouse visual treatment.',
      '- `building_massing.csv`, `layout_overlays.csv` and `street_dressing.csv` are cosmetic layout layers over stable gameplay geometry.',
      '- `light_emitters.csv` is independent from geometry and can be replaced by another lighting pack.',
      '- The callback pack contains exactly 100 master environment archetypes; day/night assets are states of those same objects, not extra object types.',
    ]
    (OUT/'QUALITATIVE_ART_REVIEW.md').write_text('\n'.join(report)+'\n',encoding='utf-8')
    print(OUT/'QUALITATIVE_ART_REVIEW.md')
if __name__=='__main__':run()
