from __future__ import annotations
import csv
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
GEN=ROOT/'dev_tools'/'map_generator'

def readkv(p):
    with p.open('r',encoding='utf-8-sig',newline='') as f:return {r['key']:r['value'] for r in csv.DictReader(f)}

def main():
    src=readkv(GEN/'config'/'source_mode.csv')
    assert src.get('source_mode')=='reference_image_set',src
    assert 'gis_enabled' not in src, 'obsolete GIS source-mode switch still present'
    req=(GEN/'requirements.txt').read_text(encoding='utf-8').lower()
    assert 'requests' not in req and 'networkx' not in req,'normal generator still has removed network-map dependencies'
    assert not (GEN/'legacy_gis').exists(),'legacy network-map directory still present'
    assert not (GEN/'SETUP_LEGACY_GIS.bat').exists(),'legacy network-map setup still present'
    assert not (GEN/'requirements_legacy_gis.txt').exists(),'legacy network-map requirements still present'
    for n,h in {
      'roads_trace.csv':'road_id,points_image_px,width_class,lane_hint,direction,notes',
      'traffic_trace.csv':'flow_id,points_image_px,priority,relative_density,direction,notes',
      'terrain_trace.csv':'area_id,terrain_type,polygon_image_px,notes',
      'transit_trace.csv':'transit_id,mode,points_image_px,station_name,notes',
      'biking_trace.csv':'bike_id,facility_type,points_image_px,direction,notes',
    }.items():
      p=GEN/'working_reference'/n
      assert p.exists(),n
      first=p.read_text(encoding='utf-8-sig').splitlines()[0]
      assert first==h,(n,first)
    for rel in ['tools/reference_map_import.py','tools/reference_map_studio.py','tools/compile_reference_map.py']:
      assert (GEN/rel).exists(),rel
    defaults=readkv(GEN/'config'/'generator_defaults.csv')
    assert defaults.get('default_preview_mode')=='night',defaults
    assert defaults.get('street_lamps_enabled','').lower()=='true',defaults
    print('REFERENCE MAP PIPELINE AUDIT: PASS')
    print(' source=reference_image_set | legacy network-map path absent | 5 trace schemas ready | night/street-lamps default')
if __name__=='__main__':main()
