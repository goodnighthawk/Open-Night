from __future__ import annotations

import csv
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mapfiles.loader import load_map_folder
from mapfiles.art_rules import audit_art_rules
from mapfiles.grid import chunk_label

MAP_DIR = ROOT / "mapfiles" / "data" / "map_001_gwb_corridor"
OUT = ROOT / "art_review" / "map_art_rule_audit.csv"


def main() -> int:
    cfg = load_map_folder(MAP_DIR)
    issues = audit_art_rules(cfg)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    # Resolve issue subjects back to map positions where possible so art fixes
    # can be discussed as e.g. "J3 @ (240,610)" rather than raw world values.
    positions: dict[str, tuple[float, float]] = {}
    for prop in cfg.get("street_props", []) or []:
        try: positions[str(prop.get("id", ""))] = (float(prop["pos"][0]), float(prop["pos"][1]))
        except Exception: pass
    for crossing in cfg.get("crosswalks", []) or []:
        try: positions[str(crossing.get("id", ""))] = (float(crossing["pos"][0]), float(crossing["pos"][1]))
        except Exception: pass
    for idx, bid in enumerate(cfg.get("building_ids", []) or []):
        if idx < len(cfg.get("buildings", []) or []):
            try:
                x,y,bw,bh=map(float,cfg["buildings"][idx][:4]); positions[str(bid)] = (x+bw*0.5,y+bh*0.5)
            except Exception: pass
    for group in ("spawns","login_spawns"):
        for idx, pos in enumerate(cfg.get(group, []) or []):
            try: positions[f"{group}[{idx}]"]=(float(pos[0]),float(pos[1]))
            except Exception: pass
    chunk_size=max(1,int(cfg.get("chunk_size",1024)))

    with OUT.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["severity", "code", "subject", "chunk_id", "local_x", "local_y", "message"])
        w.writeheader()
        for issue in issues:
            pos=positions.get(issue.subject)
            chunk_id=""; local_x=""; local_y=""
            if pos is not None:
                cx=max(0,int(pos[0]//chunk_size)); cy=max(0,int(pos[1]//chunk_size))
                chunk_id=chunk_label(cx,cy); local_x=int(pos[0]-cx*chunk_size); local_y=int(pos[1]-cy*chunk_size)
            w.writerow({"severity": issue.severity, "code": issue.code, "subject": issue.subject, "chunk_id":chunk_id, "local_x":local_x, "local_y":local_y, "message": issue.message})
    errors = sum(i.severity == "ERROR" for i in issues)
    warnings = len(issues) - errors
    print(f"Art-rule audit: errors={errors} warnings={warnings}")
    print(f"Wrote {OUT.relative_to(ROOT)}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
