from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mapfiles import load_all_maps, validate_map
from mapfiles.art_rules import audit_art_rules


def main() -> int:
    maps = load_all_maps(ROOT / "mapfiles" / "data")
    if not maps:
        print("ERROR: no CSV maps found in mapfiles/data")
        return 2
    failed = False
    for map_id, cfg in maps.items():
        errors = validate_map(cfg)
        print(f"[{map_id}] {cfg.get('name', map_id)}")
        print(f"  source: {cfg.get('data_folder', '?')}")
        print(f"  roads={len(cfg.get('roads', []))} crosswalks={len(cfg.get('crosswalks', []))} traffic_routes={len(cfg.get('traffic_routes', []))} npc_routes={len(cfg.get('npc_routes', []))} bike_lanes={len(cfg.get('bike_lanes', []))}")
        art_issues = audit_art_rules(cfg)
        art_errors = [i for i in art_issues if i.severity == "ERROR"]
        art_warnings = [i for i in art_issues if i.severity != "ERROR"]
        if errors or art_errors:
            failed = True
        for error in errors:
            print("  ERROR:", error)
        for issue in art_errors:
            print(f"  ART ERROR [{issue.code}] {issue.subject}: {issue.message}")
        for issue in art_warnings:
            print(f"  ART WARN  [{issue.code}] {issue.subject}: {issue.message}")
        if not errors and not art_errors:
            print(f"  OK (art warnings={len(art_warnings)})")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
