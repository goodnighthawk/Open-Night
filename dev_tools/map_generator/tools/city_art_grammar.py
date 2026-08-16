from __future__ import annotations

"""Reusable city-art grammar derived from the approved Open Night core.

The goal is not to copy individual approved sprites.  It encodes the urban
relationships that make the protected core read as one authored city: short
street-wall runs, clustered eras/heights, a minority of consolidated lots,
irregular massing, coherent district material families, landmarks with breathing
room, and deliberate negative space.  Numeric targets live in CSV so future map
passes can tune the grammar without rewriting generation code.
"""

import csv
import hashlib
import math
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RULES_PATH = ROOT / "config" / "city_art_rules.csv"


def stable(text: str) -> int:
    return int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:16], 16)


def load_rules(path: Path = RULES_PATH) -> dict[str, dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return {row["rule_id"]: row for row in csv.DictReader(handle)}


RULES = load_rules()


def bounds(rule_id: str) -> tuple[float, float]:
    row = RULES[rule_id]
    return float(row["target_min"]), float(row["target_max"])


def midpoint(rule_id: str) -> float:
    lo, hi = bounds(rule_id)
    return (lo + hi) * 0.5


def merged_lot_count(key: str) -> int:
    """Return 1..4 lots with a target share near the CSV midpoint.

    Consolidation changes parent footprint only.  Child windows/walls/roof
    components remain fixed physical size in the renderer.
    """
    q = stable("merged:" + key) % 10000
    share = midpoint("block_merged_lot_share")
    if q >= int(share * 10000):
        return 1
    # Most consolidated sites are two lots; rarer civic/apartment masses use 3–4.
    band = (q * 17 + stable(key + ":band")) % 100
    return 2 if band < 72 else 3 if band < 94 else 4


def massing_variant(key: str, merged: int = 1, corner: bool = False) -> str:
    """Choose a footprint family while keeping rectangles a clear minority."""
    q = stable("massing:" + key)
    if corner:
        return ("chamfer", "L", "perimeter")[q % 3]
    if merged >= 3:
        return ("U", "courtyard", "perimeter", "L")[q % 4]
    if merged == 2:
        return ("L", "U", "chamfer", "stepped", "courtyard")[q % 5]
    # ~75% irregular ordinary massing, centred in the configured 62–88% band.
    variants = ("L", "U", "chamfer", "stepped", "perimeter", "courtyard", "rect", "rect")
    return variants[q % len(variants)]


def height_band(block_id: str, building_id: str) -> str:
    """Cluster height by block, then allow a minority of local deviations."""
    base = stable("height-block:" + block_id) % 4
    q = stable("height-building:" + building_id) % 100
    if q < 72:
        band = base
    elif q < 88:
        band = max(0, base - 1)
    else:
        band = min(4, base + 1)
    return ("low", "mid_low", "mid", "mid_high", "high")[band]


def material_family(district: str, block_id: str, building_id: str) -> str:
    """Reuse a small district palette while avoiding exact building repetition."""
    family_count = int(round(midpoint("art_material_family")))
    family_count = max(4, min(8, family_count))
    # Block seed dominates so neighbors share an era; building seed introduces
    # controlled variation inside that era.
    block_family = stable(f"material:{district}:{block_id}") % family_count
    if stable("material-local:" + building_id) % 100 < 68:
        idx = block_family
    else:
        idx = (block_family + 1 + stable(building_id) % 2) % family_count
    return f"{district}_family_{idx+1:02d}"


def block_id_for(x: float, y: float, district: str, cell: int = 520) -> str:
    # Offset every second row so grammar cells do not produce a visible perfect grid.
    gy = int(math.floor(y / cell))
    gx = int(math.floor((x - (cell * 0.34 if gy % 2 else 0.0)) / cell))
    return f"{district}_b{gx:+03d}_{gy:+03d}"


def frontage_run_id(block_id: str, x: float, y: float) -> str:
    # 2–6 neighboring buildings should share a run; grouping by a coarser phase
    # creates repeated street-wall sequences without identical sprites.
    phase = int((x + 0.65 * y) // 180) % 6
    return f"{block_id}_run_{phase:02d}"


def candidate_size(key: str, merged: int) -> tuple[int, int]:
    q = stable("size:" + key)
    if merged >= 3:
        return 220 + q % 86, 150 + (q >> 8) % 78
    if merged == 2:
        return 170 + q % 72, 120 + (q >> 8) % 64
    return 108 + q % 58, 90 + (q >> 8) % 52


def grammar_metadata(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    out = []
    for row in rows:
        x=float(row["x"]); y=float(row["y"]); w=float(row["w"]); h=float(row["h"])
        district=row.get("district", "urban") or "urban"
        bid=row["building_id"]
        block=block_id_for(x+w*.5, y+h*.5, district)
        run=frontage_run_id(block, x+w*.5, y+h*.5)
        merged=int(float(row.get("merged_lot_count",1) or 1))
        out.append({
            "building_id": bid,
            "block_id": block,
            "frontage_run_id": run,
            "height_band": height_band(block,bid),
            "material_family": material_family(district,block,bid),
            "massing_variant": massing_variant(bid,merged),
            "merged_lot_count": str(merged),
            "city_grammar_version": "approved_core_v1",
        })
    return out


def grammar_summary(assignments: list[dict[str,str]]) -> dict[str,float]:
    if not assignments:
        return {"buildings":0,"merged_share":0.0,"irregular_share":0.0,"max_material_share":0.0,"height_cluster_share":0.0}
    n=len(assignments)
    merged=sum(int(r["merged_lot_count"])>=2 for r in assignments)/n
    irregular=sum(r["massing_variant"]!="rect" for r in assignments)/n
    mats=defaultdict(int); blocks=defaultdict(list)
    for r in assignments:
        mats[r["material_family"]]+=1; blocks[r["block_id"]].append(r)
    max_mat=max(mats.values())/n
    matched=total=0
    for rows in blocks.values():
        if len(rows)<2: continue
        counts=defaultdict(int)
        for r in rows:counts[r["height_band"]]+=1
        matched += max(counts.values()); total += len(rows)
    return {
        "buildings":float(n),
        "merged_share":merged,
        "irregular_share":irregular,
        "max_material_share":max_mat,
        "height_cluster_share":matched/max(1,total),
    }
