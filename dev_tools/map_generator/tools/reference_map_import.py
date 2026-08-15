from __future__ import annotations
import argparse,csv,hashlib
from datetime import datetime, timezone
from pathlib import Path
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parents[1]
REF=ROOT/'references'/'street_map_reference.png'
LAYER_DIR=ROOT/'references'/'layers'
MANIFEST=ROOT/'working_reference'/'reference_image_manifest.csv'
LAYER_MANIFEST=ROOT/'working_reference'/'reference_layer_manifest.csv'
PREVIEW=ROOT/'output'/'reference_map_alignment.png'
COMPOSITE=ROOT/'output'/'reference_map_composite.png'
SETTINGS=ROOT/'config'/'reference_map_settings.csv'
LAYERS=('roads','traffic','terrain','transit','biking')

def settings():
    with SETTINGS.open('r',encoding='utf-8-sig',newline='') as f:
        return {r['key']:r['value'] for r in csv.DictReader(f)}

def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
    return h.hexdigest()

def write_manifest(src:Path,img:Image.Image, contract='single composite reference image'):
    MANIFEST.parent.mkdir(parents=True,exist_ok=True)
    rows=[('source_filename',src.name),('normalized_path',str(REF.relative_to(ROOT)).replace('\\','/')),
          ('image_width_px',str(img.width)),('image_height_px',str(img.height)),('sha256',sha(REF)),
          ('imported_utc',datetime.now(timezone.utc).isoformat()),('input_contract',contract)]
    with MANIFEST.open('w',encoding='utf-8',newline='') as f:
        w=csv.writer(f);w.writerow(['key','value']);w.writerows(rows)

def _layer_rows():
    if not LAYER_MANIFEST.exists(): return []
    with LAYER_MANIFEST.open('r',encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))

def _write_layer_rows(rows):
    LAYER_MANIFEST.parent.mkdir(parents=True,exist_ok=True)
    fields=['layer','path','source_filename','width_px','height_px','sha256','imported_utc','opacity','visible']
    with LAYER_MANIFEST.open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)

def import_layer(layer:str,src:Path):
    layer=layer.lower().strip()
    if layer not in LAYERS: raise SystemExit('Layer must be one of: '+', '.join(LAYERS))
    src=src.expanduser().resolve()
    if not src.is_file(): raise SystemExit(f'Image not found: {src}')
    with Image.open(src) as raw: img=raw.convert('RGB')
    LAYER_DIR.mkdir(parents=True,exist_ok=True); dst=LAYER_DIR/f'{layer}.png';img.save(dst,optimize=True)
    rows=[r for r in _layer_rows() if r.get('layer')!=layer]
    default_opacity={'roads':'1.0','traffic':'0.72','terrain':'0.65','transit':'0.72','biking':'0.72'}[layer]
    rows.append({'layer':layer,'path':str(dst.relative_to(ROOT)).replace('\\','/'),'source_filename':src.name,
                 'width_px':str(img.width),'height_px':str(img.height),'sha256':sha(dst),
                 'imported_utc':datetime.now(timezone.utc).isoformat(),'opacity':default_opacity,'visible':'true'})
    rows.sort(key=lambda r:LAYERS.index(r['layer']))
    _write_layer_rows(rows)
    # Roads defines base alignment when available; otherwise first imported layer does.
    if layer=='roads' or not REF.exists():
        img.save(REF,optimize=True);write_manifest(src,img,'aligned roads/traffic/terrain/transit/biking screenshot set')
    build_composite(); alignment_preview(Image.open(REF).convert('RGB'))
    print(f'Imported {layer} reference:',dst)

def import_image(src:Path):
    src=src.expanduser().resolve()
    if not src.is_file(): raise SystemExit(f'Image not found: {src}')
    with Image.open(src) as raw: img=raw.convert('RGB')
    REF.parent.mkdir(parents=True,exist_ok=True);img.save(REF,optimize=True)
    write_manifest(src,img,'single composite roads+traffic+terrain+transit+biking reference')
    alignment_preview(img);print('Composite reference installed:',REF)

def build_composite():
    rows=_layer_rows()
    if not rows: return None
    base_path=LAYER_DIR/'roads.png'
    if not base_path.exists(): base_path=ROOT/rows[0]['path']
    with Image.open(base_path) as raw: base=raw.convert('RGBA')
    for row in rows:
        if row['layer']=='roads' or str(row.get('visible','true')).lower() not in {'1','true','yes','on'}: continue
        p=ROOT/row['path']
        if not p.exists(): continue
        with Image.open(p) as raw:
            layer=raw.convert('RGBA').resize(base.size,Image.Resampling.LANCZOS)
        alpha=max(0,min(255,round(float(row.get('opacity','0.7'))*255)))
        layer.putalpha(alpha); base=Image.alpha_composite(base,layer)
    COMPOSITE.parent.mkdir(parents=True,exist_ok=True);base.convert('RGB').save(COMPOSITE,optimize=True)
    return COMPOSITE

def alignment_preview(img:Image.Image):
    s=settings(); cols=max(1,int(s.get('reference_grid_columns','12'))); rows=max(1,int(s.get('reference_grid_rows','4')))
    out=img.convert('RGB').copy(); d=ImageDraw.Draw(out,'RGBA')
    for i in range(1,cols):
        x=round(i*out.width/cols); d.line((x,0,x,out.height),fill=(255,220,80,125),width=max(1,out.width//1200))
    for i in range(1,rows):
        y=round(i*out.height/rows); d.line((0,y,out.width,y),fill=(255,220,80,125),width=max(1,out.width//1200))
    label='OPEN NIGHT REFERENCE // ROADS + TRAFFIC + TERRAIN + TRANSIT + BIKING'
    box_h=max(28,out.height//18);d.rectangle((0,0,out.width,box_h),fill=(0,0,0,175));d.text((12,7),label,fill=(255,245,210,255))
    PREVIEW.parent.mkdir(parents=True,exist_ok=True);out.save(PREVIEW)

def status():
    print('Primary source mode: reference_image_set')
    print('Base reference:',REF,'FOUND' if REF.exists() else 'MISSING')
    print('Layer references:')
    rows={r['layer']:r for r in _layer_rows()}
    for layer in LAYERS:
        r=rows.get(layer);print(f'  {layer:8}: '+(f"{r['source_filename']} ({r['width_px']}x{r['height_px']})" if r else 'MISSING / optional'))
    print('Trace layers:')
    for n in ('roads_trace.csv','traffic_trace.csv','terrain_trace.csv','transit_trace.csv','biking_trace.csv'):
        p=ROOT/'working_reference'/n;count=max(0,sum(1 for _ in p.open(encoding='utf-8-sig'))-1) if p.exists() else 0
        print(f'  {n}: {count} authored rows')
    print('GIS/Overpass: removed; reference screenshots are the only map-source workflow.')

def main():
    ap=argparse.ArgumentParser(description='Open Night street-map screenshot importer')
    sp=ap.add_subparsers(dest='cmd',required=True)
    p=sp.add_parser('import');p.add_argument('image')
    p=sp.add_parser('import-layer');p.add_argument('layer',choices=LAYERS);p.add_argument('image')
    sp.add_parser('build-composite');sp.add_parser('status')
    a=ap.parse_args()
    if a.cmd=='import': import_image(Path(a.image))
    elif a.cmd=='import-layer': import_layer(a.layer,Path(a.image))
    elif a.cmd=='build-composite': print(build_composite() or 'No layer images imported')
    else: status()
if __name__=='__main__':main()
