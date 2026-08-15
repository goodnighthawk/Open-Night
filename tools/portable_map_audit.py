import io
import zipfile
from pathlib import Path
import sys
from PIL import Image
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
if not cfg.get('baked_composition_archive'):
    raise SystemExit('Portable map resolved no baked composition archive')
archive_path = Path(str(cfg['baked_composition_archive']))
decoded_tiles = 0
with zipfile.ZipFile(archive_path, 'r') as archive:
    for name in archive.namelist():
        if not name.endswith('.png'):
            continue
        image = Image.open(io.BytesIO(archive.read(name)))
        image.load()
        decoded_tiles += 1
if decoded_tiles != 64:
    raise SystemExit(f'Portable baked composition has {decoded_tiles} PNG tiles; expected 64')
transfer = build_transfer_bundle(MAP)
print('PORTABLE MAP AUDIT: PASS')
print(f" map: {cfg['name']} / {transfer['hash'][:16]}...")
print(f" roads={len(cfg.get('roads',[]))} props={len(cfg.get('street_props',[]))} baked_composition=yes lights={len(cfg.get('portable_light_emitters',[]))}")
print(f" transfer_package={transfer['size_bytes']} bytes / decoded_tiles={decoded_tiles}")
