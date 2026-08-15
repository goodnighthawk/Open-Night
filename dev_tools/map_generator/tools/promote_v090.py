from __future__ import annotations

"""Promote the visually approved balanced Pass 19 map as Open Night v0.9.0.

The promotion is intentionally guarded: it refuses to package stale Pass 18 or
unbalanced Pass 19 output.  Runtime metadata points to composition_tiles_v19.zip;
a v18-named compatibility alias is retained with identical v0.9.0 art so older
portable-map readers cannot silently fall back to stale artwork.
"""

import csv
import shutil
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import build_unified_composition as composition
import promote_unified_composition as legacy

ROOT = Path(__file__).resolve().parents[3]
SEMANTIC = composition.SEMANTIC
COMPOSITION = composition.OUT
APPROVED_DIR = ROOT / "assets" / "environment" / "approved" / "map_001_gwb_corridor"
V19_ARCHIVE = APPROVED_DIR / "composition_tiles_v19.zip"
V18_COMPAT_ARCHIVE = APPROVED_DIR / "composition_tiles_v18.zip"
MAP_DIRS = legacy.MAP_DIRS
EXPECTED_PASS = "art_convergence_pass_19b_frontage_balanced"


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def gate_release_candidate() -> dict[str, int]:
    manifest = {row.get("key", ""): row.get("value", "") for row in read_csv(COMPOSITION / "composition_manifest.csv")}
    if manifest.get("pass_id") != EXPECTED_PASS:
        raise RuntimeError(
            f"Refusing v0.9.0 promotion: expected {EXPECTED_PASS!r}, got {manifest.get('pass_id')!r}"
        )
    buildings = read_csv(SEMANTIC / "iterated_buildings.csv")
    vegetation = read_csv(SEMANTIC / "iterated_vegetation.csv")
    frontage = read_csv(SEMANTIC / "iterated_frontage_dressing.csv")
    scales = read_csv(SEMANTIC / "building_sprite_scale_audit.csv")
    if len(buildings) != 95:
        raise RuntimeError(f"Refusing v0.9.0 promotion: expected 95 buildings, got {len(buildings)}")
    failures = [row for row in scales if row.get("status") != "pass"]
    if failures:
        raise RuntimeError(f"Refusing v0.9.0 promotion: {len(failures)} building scale failures")
    park_trees = [row for row in vegetation if row.get("placement_rule") == "retained_park_canopy_pass19_v2"]
    obvious = [row for row in frontage if row.get("kind") not in {"frontage_wear", "litter_cluster"}]
    dressed = {row.get("building_id") for row in obvious}
    counts: dict[str, int] = defaultdict(int)
    for row in obvious:
        counts[str(row.get("building_id", ""))] += 1
    cluttered = {bid for bid, count in counts.items() if count >= 4}
    if len(park_trees) < 20:
        raise RuntimeError(f"Refusing v0.9.0 promotion: only {len(park_trees)} park-canopy trees")
    if not 29 <= len(dressed) <= 48:
        raise RuntimeError(f"Refusing v0.9.0 promotion: dressed facades={len(dressed)} outside 30-50% target")
    if not 10 <= len(cluttered) <= 19:
        raise RuntimeError(f"Refusing v0.9.0 promotion: cluttered facades={len(cluttered)} outside 10-20% target")
    return {
        "buildings": len(buildings),
        "vegetation": len(vegetation),
        "park_trees": len(park_trees),
        "frontage_rows": len(frontage),
        "dressed": len(dressed),
        "cluttered": len(cluttered),
    }


_original_map_rows = legacy.map_rows
_original_write_csv = legacy.write_csv


def v090_map_rows() -> list[dict[str, str]]:
    rows = _original_map_rows()
    replacements = {
        "description": "Pass 19 balanced art-convergence corridor; the default and only playable map for Open Night v0.9.0.",
        "baked_composition_archive": "assets/environment/approved/map_001_gwb_corridor/composition_tiles_v19.zip",
        "map_build_id": "open_night_v0_9_0_pass19_default_only",
        "render_pass": "19",
        "building_cosmetic_rule": "pass19_native_scale_anti_repetition_v1",
    }
    for row in rows:
        key = row.get("key", "")
        if key in replacements:
            row["value"] = replacements[key]
    rows.extend([
        {"key": "vegetation_cosmetic_rule", "value": "retained_park_canopy_pass19_v2", "type": "str"},
        {"key": "frontage_cosmetic_rule", "value": "district_frontage_cluster_pass19b_balanced_v1", "type": "str"},
        {"key": "frontage_collision", "value": "false", "type": "bool"},
        {"key": "release_version", "value": "0.9.0", "type": "str"},
    ])
    return rows


def v090_write_csv(path: Path, fields, rows) -> None:
    materialized = list(rows)
    if Path(path).name == "render_contract.csv":
        found = False
        for row in materialized:
            if row.get("key") == "render_pass":
                row["value"] = "19"
                found = True
        if not found:
            materialized.append({"key": "render_pass", "value": "19", "type": "int"})
    _original_write_csv(path, fields, materialized)


def copy_cosmetic_audits() -> None:
    names = (
        "iterated_vegetation.csv",
        "iterated_frontage_dressing.csv",
        "building_sprite_scale_audit.csv",
    )
    for folder in MAP_DIRS:
        for name in names:
            source = SEMANTIC / name
            if source.exists():
                shutil.copy2(source, folder / name)
        manifest = COMPOSITION / "composition_manifest.csv"
        if manifest.exists():
            shutil.copy2(manifest, folder / "composition_manifest.csv")


def main() -> None:
    stats = gate_release_candidate()
    legacy.ART_ARCHIVE = V19_ARCHIVE
    legacy.map_rows = v090_map_rows
    legacy.write_csv = v090_write_csv
    legacy.main()

    if not V19_ARCHIVE.is_file() or V19_ARCHIVE.stat().st_size <= 0:
        raise RuntimeError("v0.9.0 archive was not produced")
    # Compatibility only: both names contain identical Pass 19 art. New runtime
    # metadata always points to v19.
    shutil.copy2(V19_ARCHIVE, V18_COMPAT_ARCHIVE)
    copy_cosmetic_audits()
    (ROOT / "VERSION.txt").write_text(
        "Open Night v0.9.0 - Pass 19 balanced art-convergence corridor promoted as the default and only map\n",
        encoding="utf-8",
    )
    print(
        "PROMOTED_V090 "
        + " ".join(f"{key}={value}" for key, value in stats.items())
        + f" archive={V19_ARCHIVE.stat().st_size} compat_archive={V18_COMPAT_ARCHIVE.stat().st_size}"
    )


if __name__ == "__main__":
    main()
