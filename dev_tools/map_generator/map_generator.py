from __future__ import annotations
import argparse,csv,shutil,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent

def generator_defaults():
    rows,_=read_rows(ROOT/'config'/'generator_defaults.csv') if (ROOT/'config'/'generator_defaults.csv').exists() else ([],[])
    return {str(r.get('key','')).strip():str(r.get('value','')).strip() for r in rows if r.get('key')}

def _truthy(v): return str(v).strip().lower() in {'1','true','yes','y','on'}

def read_rows(p):
    with p.open('r',encoding='utf-8-sig',newline='') as f:r=csv.DictReader(f);return list(r),list(r.fieldnames or [])
def write_rows(p,rows,fields):
    with p.open('w',encoding='utf-8-sig',newline='') as f:w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
def run(*parts):
    return subprocess.call([sys.executable,*map(str,parts)],cwd=ROOT)
def apply_profile(name='approved_nyc_callback_v3'):
    profiles={r['profile']:r for r in read_rows(ROOT/'config'/'style_profiles.csv')[0]};p=profiles[name];path=ROOT/'config'/'map_geometry_settings.csv';rows,fields=read_rows(path);by={r['key']:r for r in rows}
    keys=['lane_multiplier','sidewalk_multiplier','road_lane_width_px','road_edge_margin_px','building_size_scale','max_lanes_motorway','max_lanes_trunk','max_lanes_primary','max_lanes_secondary','max_lanes_tertiary','max_lanes_residential','max_lanes_service']
    for k in keys:
        if k in p and str(p[k]).strip():
            if k not in by:
                rows.append({'key':k,'value':p[k],'type':'float','description':'map_generator geometry-profile override'});by[k]=rows[-1]
            else:by[k]['value']=p[k]
    write_rows(path,rows,fields)
    print(f'Applied geometry profile: {name} (reference-image semantic geometry)')
    print('Profile settings updated. Recompile/install the reference map to apply geometry changes.')
def run_reference(*args):
    return subprocess.call([sys.executable,str(ROOT/'tools'/'reference_map_import.py'),*map(str,args)],cwd=ROOT)

def build_cosmetics():
    rc=run(ROOT/'tools'/'build_cosmetic_layers.py')
    if rc:return rc
    rc=run(ROOT/'tools'/'build_layout_design.py')
    if rc:return rc
    rc=run(ROOT/'tools'/'render_callback_preview.py')
    if rc:return rc
    rc=run(ROOT/'tools'/'render_layout_preview.py')
    if rc:return rc
    rc=run(ROOT/'tools'/'qualitative_review.py')
    if rc:return rc
    d=generator_defaults()
    if _truthy(d.get('auto_export_map','true')):
        from portable_map import export_portable
        out=ROOT/d.get('map_export_directory','exports'); name=d.get('map_export_name','Map_001_GWB')
        mp,_=export_portable(out,name); print('Auto-exported portable map:',mp)
    return 0
def export_game(game):
    game=Path(game).expanduser().resolve()
    if not game.exists() or not (game/'server.py').exists():raise SystemExit('Game folder must contain server.py')
    src=ROOT/'mapfiles'/'data'/'map_001_gwb_corridor';dst=game/'mapfiles'/'data'/'map_001_gwb_corridor';backup=game/'map_generator_backups'/'map_001_gwb_corridor';backup.parent.mkdir(parents=True,exist_ok=True)
    if dst.exists():
        if backup.exists():shutil.rmtree(backup)
        shutil.copytree(dst,backup);shutil.rmtree(dst)
    shutil.copytree(src,dst)
    pack_src=ROOT/'cosmetic_packs'/'nyc_gta2_callback';pack_dst=game/'cosmetic_packs'/'nyc_gta2_callback';pack_dst.parent.mkdir(parents=True,exist_ok=True)
    if pack_dst.exists():shutil.rmtree(pack_dst)
    shutil.copytree(pack_src,pack_dst)
    layers_dst=game/'mapfiles'/'cosmetics'/'map_001_gwb_corridor';layers_dst.parent.mkdir(parents=True,exist_ok=True)
    if layers_dst.exists():shutil.rmtree(layers_dst)
    shutil.copytree(ROOT/'working_cosmetics',layers_dst)
    print('Exported semantic map + independent nyc_gta2_callback cosmetic pack to',game)
def main():
    ap=argparse.ArgumentParser(description='Open Night standalone map + sprite generator v0.5.1 screenshot-reference compiler')
    sp=ap.add_subparsers(dest='cmd',required=True)
    sp.add_parser('build-cosmetics');sp.add_parser('preview');sp.add_parser('audit');sp.add_parser('build-pack');sp.add_parser('build-layout')
    p=sp.add_parser('apply-profile');p.add_argument('profile',nargs='?',default='approved_nyc_callback_v3')
    p=sp.add_parser('import-reference');p.add_argument('image')
    p=sp.add_parser('import-reference-layer');p.add_argument('layer',choices=['roads','traffic','terrain','transit','biking']);p.add_argument('image')
    sp.add_parser('reference-status');sp.add_parser('reference-studio');sp.add_parser('compile-reference');p=sp.add_parser('install-reference');
    p=sp.add_parser('export-game');p.add_argument('game_folder')
    p=sp.add_parser('export-map');p.add_argument('output_dir',nargs='?',default=str(ROOT/'exports'));p.add_argument('--name',default='Map_001_GWB')
    p=sp.add_parser('validate-map');p.add_argument('map_file')
    a=ap.parse_args()
    if a.cmd=='build-cosmetics':raise SystemExit(build_cosmetics())
    if a.cmd=='build-pack':
        from cosmetic_pack import build_pack
        print(f'Built {len(build_pack())} master cosmetic archetypes')
    elif a.cmd=='build-layout':raise SystemExit(run(ROOT/'tools'/'build_layout_design.py'))
    elif a.cmd=='preview':
        mode=generator_defaults().get('default_preview_mode','night')
        raise SystemExit(run(ROOT/'tools'/'render_callback_preview.py','--mode',mode))
    elif a.cmd=='audit':raise SystemExit(run(ROOT/'tools'/'qualitative_review.py'))
    elif a.cmd=='apply-profile':apply_profile(a.profile)
    elif a.cmd=='import-reference':raise SystemExit(run_reference('import',a.image))
    elif a.cmd=='import-reference-layer':raise SystemExit(run_reference('import-layer',a.layer,a.image))
    elif a.cmd=='reference-status':raise SystemExit(run_reference('status'))
    elif a.cmd=='reference-studio':raise SystemExit(run(ROOT/'tools'/'reference_map_studio.py'))
    elif a.cmd=='compile-reference':raise SystemExit(run(ROOT/'tools'/'compile_reference_map.py'))
    elif a.cmd=='install-reference':raise SystemExit(run(ROOT/'tools'/'compile_reference_map.py','--install'))
    elif a.cmd=='export-game':export_game(a.game_folder)
    elif a.cmd=='export-map':
        from portable_map import export_portable,validate_portable
        mp,assets=export_portable(Path(a.output_dir),a.name);print('Portable map:',mp);print('Editable assets:',assets);print(validate_portable(mp,verify_hashes=True))
    elif a.cmd=='validate-map':
        from portable_map import validate_portable
        r=validate_portable(Path(a.map_file),verify_hashes=False);print(r);raise SystemExit(0 if r['ok'] else 2)
if __name__=='__main__':main()
