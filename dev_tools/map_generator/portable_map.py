from __future__ import annotations

import csv
import hashlib
import json
import shutil
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parent
MAP_DIR = ROOT / 'mapfiles' / 'data' / 'map_001_gwb_corridor'
COS_DIR = ROOT / 'working_cosmetics'
PACK_ID = 'nyc_gta2_callback'
PACK_DIR = ROOT / 'cosmetic_packs' / PACK_ID
DEFAULT_EXPORT_NAME = 'Map_001_GWB'
FORMAT = 'PYMMO_PORTABLE_MAP'
FORMAT_VERSION = 1


def _read_csv(path: Path):
    with path.open('r', encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def _sha256(path: Path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def _role(rel: Path):
    p = rel.as_posix()
    if p.startswith('composition/'): return 'baked_map_composition'
    if p.startswith('textures/objects/'): return 'object_sprite'
    if p.startswith('textures/materials/'): return 'surface_material'
    if p.startswith('signs/'): return 'sign_texture'
    if p.startswith('lighting/'): return 'lighting_texture'
    if p.startswith('atlases/'): return 'sprite_atlas'
    if p.endswith('.csv'): return 'catalog'
    return 'asset'


def _copy_pack_assets(asset_root: Path):
    if asset_root.exists(): shutil.rmtree(asset_root)
    (asset_root / 'textures' / 'objects').mkdir(parents=True, exist_ok=True)
    (asset_root / 'textures' / 'materials').mkdir(parents=True, exist_ok=True)
    (asset_root / 'signs').mkdir(parents=True, exist_ok=True)
    (asset_root / 'lighting').mkdir(parents=True, exist_ok=True)
    (asset_root / 'atlases').mkdir(parents=True, exist_ok=True)
    (asset_root / 'catalogs').mkdir(parents=True, exist_ok=True)
    (asset_root / 'composition').mkdir(parents=True, exist_ok=True)

    # Individual PNG files are deliberately preserved for direct editing/modding.
    for p in sorted((PACK_DIR / 'sprites').glob('*.png')):
        shutil.copy2(p, asset_root / 'textures' / 'objects' / p.name)
    for p in sorted((PACK_DIR / 'materials').glob('*.png')):
        shutil.copy2(p, asset_root / 'textures' / 'materials' / p.name)
    for p in sorted((PACK_DIR / 'signs').glob('*.png')):
        shutil.copy2(p, asset_root / 'signs' / p.name)
    for p in sorted((PACK_DIR / 'lighting').glob('*.png')):
        shutil.copy2(p, asset_root / 'lighting' / p.name)
    map_meta={r.get('key',''):r.get('value','') for r in _read_csv(MAP_DIR/'map.csv') if r.get('key')}
    composition_rel=Path(map_meta.get('baked_composition_archive','assets/environment/approved/map_001_gwb_corridor/composition_tiles_v19.zip'))
    composition_src=ROOT.parent.parent/composition_rel
    for src, dst in [
        (PACK_DIR / 'sprite_atlas_day.png', asset_root / 'atlases' / 'sprite_atlas_day.png'),
        (PACK_DIR / 'sprite_atlas_night.png', asset_root / 'atlases' / 'sprite_atlas_night.png'),
        (PACK_DIR / 'object_catalog.csv', asset_root / 'catalogs' / 'object_catalog.csv'),
        (PACK_DIR / 'atlas_index.csv', asset_root / 'catalogs' / 'atlas_index.csv'),
        (composition_src, asset_root / 'composition' / composition_src.name),
    ]:
        if src.exists(): shutil.copy2(src, dst)

    # Rewrite catalog paths to portable asset-root-relative paths.
    cat_path = asset_root / 'catalogs' / 'object_catalog.csv'
    if cat_path.exists():
        rows = _read_csv(cat_path)
        for r in rows:
            r['day_sprite'] = 'textures/objects/' + Path(r['day_sprite']).name
            r['night_sprite'] = 'textures/objects/' + Path(r['night_sprite']).name
        with cat_path.open('w', encoding='utf-8-sig', newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0]) if rows else [],lineterminator='\n');w.writeheader();w.writerows(rows)

    manifest=[]
    for p in sorted(x for x in asset_root.rglob('*') if x.is_file()):
        rel=p.relative_to(asset_root)
        manifest.append({'path':rel.as_posix(),'role':_role(rel),'size_bytes':p.stat().st_size,'sha256':_sha256(p)})
    mf=asset_root/'manifest.csv'
    with mf.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=['path','role','size_bytes','sha256'],lineterminator='\n');w.writeheader();w.writerows(manifest)
    return manifest


def build_document(export_name: str, asset_dir_name: str):
    map_tables={}
    for p in sorted(MAP_DIR.glob('*.csv')):
        map_tables[p.stem]=_read_csv(p)
    cosmetic_tables={}
    for p in sorted(COS_DIR.glob('*.csv')):
        cosmetic_tables[p.stem]=_read_csv(p)
    map_meta={r.get('key',''):r.get('value','') for r in map_tables.get('map',[]) if r.get('key')}
    return {
        'format':FORMAT,
        'format_version':FORMAT_VERSION,
        'generator_version':'0.4.0',
        'map_id':map_meta.get('id','map_001_gwb_corridor'),
        'display_name':map_meta.get('name','Map 001 — Fort Lee / GWB / Washington Heights'),
        'asset_root':asset_dir_name,
        'cosmetic_pack':PACK_ID,
        'default_render_mode':'night',
        'default_lighting_profile':'night_callback',
        'street_lamps_enabled':True,
        'art_contract':{
            'gameplay_geometry_is_authoritative':True,
            'cosmetics_are_replaceable':True,
            'lighting_is_independent':True,
            'paths_are_relative_to_map_file':True,
            'object_archetype_budget':100,
            'layout_dressing_is_cosmetic':True,
        },
        'tables':map_tables,
        'cosmetics':cosmetic_tables,
        'notes':[
            'Move this .map file together with its sibling *_assets folder.',
            'PNG files inside the asset folder may be edited directly without changing gameplay object IDs.',
            'Rebuild the atlas after individual-object edits only if a client chooses atlas rendering; individual sprite paths remain canonical.',
            'building_massing/layout_overlays/street_dressing are cosmetic layout layers and do not change authoritative collision or network IDs.',
        ],
    }


def export_portable(output_dir: Path, export_name: str = DEFAULT_EXPORT_NAME):
    output_dir=Path(output_dir).expanduser().resolve(); output_dir.mkdir(parents=True,exist_ok=True)
    asset_dir_name=f'{export_name}_assets'; asset_root=output_dir/asset_dir_name
    if not PACK_DIR.exists():
        from cosmetic_pack import build_pack
        build_pack()
    if not (COS_DIR/'cosmetic_instances.csv').exists():
        from tools.build_cosmetic_layers import build
        build()
    if not (COS_DIR/'building_massing.csv').exists():
        from tools.build_layout_design import build as build_layout
        build_layout()
    manifest=_copy_pack_assets(asset_root)
    doc=build_document(export_name,asset_dir_name)
    doc['asset_manifest']=[{'path':r['path'],'role':r['role'],'size_bytes':r['size_bytes'],'sha256':r['sha256']} for r in manifest]
    map_path=output_dir/f'{export_name}.map'
    map_path.write_text(json.dumps(doc,indent=2,ensure_ascii=False),encoding='utf-8')
    return map_path, asset_root


def validate_portable(map_path: Path, verify_hashes=True):
    map_path=Path(map_path).expanduser().resolve()
    data=json.loads(map_path.read_text(encoding='utf-8'))
    errors=[]
    if data.get('format')!=FORMAT: errors.append(f'Unexpected format: {data.get("format")}')
    if int(data.get('format_version',0))!=FORMAT_VERSION: errors.append(f'Unsupported format version: {data.get("format_version")}')
    asset_root=map_path.parent/data.get('asset_root','')
    if not asset_root.is_dir(): errors.append(f'Asset folder missing: {asset_root}')
    else:
        for row in data.get('asset_manifest',[]):
            p=asset_root/row['path']
            if not p.is_file(): errors.append(f'Missing asset: {row["path"]}'); continue
            if verify_hashes and row.get('sha256') and _sha256(p)!=row['sha256']:
                errors.append(f'Hash changed: {row["path"]}')
    return {'ok':not errors,'errors':errors,'map_path':str(map_path),'asset_root':str(asset_root),'table_count':len(data.get('tables',{})),'cosmetic_table_count':len(data.get('cosmetics',{}))}


if __name__=='__main__':
    p,a=export_portable(ROOT/'exports')
    print(p); print(a); print(validate_portable(p))
