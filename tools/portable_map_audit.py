from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
from portable_map_runtime import validate_portable_map, load_portable_map, build_transfer_bundle

MAP = ROOT / 'dev_tools' / 'map_generator' / 'exports' / 'Map_001_GWB.map'
errors = validate_portable_map(MAP, verify_hashes=True)
if errors:
    raise SystemExit('PORTABLE MAP AUDIT FAILED:\n' + '\n'.join(errors[:20]))
cfg = load_portable_map(MAP)
if str(cfg.get('default_render_mode')).lower() != 'night':
    raise SystemExit('Portable map default render mode is not night')
if not cfg.get('street_lamps_enabled', False):
    raise SystemExit('Portable map street lamps are not enabled')
if not cfg.get('portable_prop_sprites'):
    raise SystemExit('Portable map resolved no cached prop textures')
transfer = build_transfer_bundle(MAP)
print('PORTABLE MAP AUDIT: PASS')
print(f" map: {cfg['name']} / {transfer['hash'][:16]}...")
print(f" roads={len(cfg.get('roads',[]))} props={len(cfg.get('street_props',[]))} portable_textures={len(cfg.get('portable_prop_sprites',{}))} lights={len(cfg.get('portable_light_emitters',[]))}")
print(f" transfer_package={transfer['size_bytes']} bytes")
