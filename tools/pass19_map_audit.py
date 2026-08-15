from __future__ import annotations

import csv
import json
import subprocess
import sys
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAP = ROOT / "mapfiles" / "data" / "map_001_gwb_corridor"
GENERATOR = ROOT / "dev_tools" / "map_generator"
GENERATOR_MAP = GENERATOR / "mapfiles" / "data" / "map_001_gwb_corridor"
PORTABLE = GENERATOR / "exports" / "Map_001_GWB.map"
PORTABLE_ASSETS = GENERATOR / "exports" / "Map_001_GWB_assets"
COMPOSITION = (
    ROOT
    / "assets"
    / "environment"
    / "approved"
    / "map_001_gwb_corridor"
    / "composition_tiles_v19.zip"
)


def rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def key_values(path: Path) -> dict[str, str]:
    return {row["key"]: row["value"] for row in rows(path)}


def main() -> int:
    metadata = key_values(MAP / "map.csv")
    contract = key_values(MAP / "render_contract.csv")
    assert metadata.get("render_pass") == "19", metadata.get("render_pass")
    assert contract.get("render_pass") == "19", contract.get("render_pass")
    assert metadata.get("map_build_id") == "open_night_v0_8_1_pass19_default_only"
    assert metadata.get("baked_composition_archive", "").endswith(
        "composition_tiles_v19.zip"
    )
    assert (
        metadata.get("building_cosmetic_rule")
        == "district_native_scale_anti_repetition_v3"
    )
    assert metadata.get("yellow_center_lines", "").lower() == "false"

    mirror_tables = (
        "map.csv",
        "render_contract.csv",
        "buildings.csv",
        "building_sprites.csv",
        "building_layers.csv",
        "building_stairwells.csv",
    )
    for relative in mirror_tables:
        assert (MAP / relative).read_bytes() == (GENERATOR_MAP / relative).read_bytes(), (
            f"generator/runtime mismatch: {relative}"
        )

    assert COMPOSITION.is_file(), f"missing Pass 19 composition: {COMPOSITION}"
    with zipfile.ZipFile(COMPOSITION) as archive:
        names = archive.namelist()
        assert archive.testzip() is None, "Pass 19 composition ZIP is corrupt"
        day_tiles = [name for name in names if name.startswith("day/")]
        night_tiles = [name for name in names if name.startswith("night/")]
        assert len(day_tiles) == 32, f"expected 32 day tiles, found {len(day_tiles)}"
        assert len(night_tiles) == 32, f"expected 32 night tiles, found {len(night_tiles)}"

    convergence = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "building_art_convergence_audit.py"), "--strict"],
        cwd=ROOT,
        check=False,
    )
    assert convergence.returncode == 0, "Pass 19 building-art convergence gate failed"

    document = json.loads(PORTABLE.read_text(encoding="utf-8"))
    portable_metadata = {
        row["key"]: row["value"] for row in document["tables"]["map"]
    }
    portable_contract = {
        row["key"]: row["value"]
        for row in document["tables"]["render_contract"]
    }
    assert portable_metadata.get("render_pass") == "19"
    assert portable_contract.get("render_pass") == "19"
    assert (
        portable_metadata.get("map_build_id")
        == "open_night_v0_8_1_pass19_default_only"
    )
    assert len(document["tables"]["building_sprites"]) == 95
    composition_assets = [
        row["path"]
        for row in document.get("asset_manifest", [])
        if row.get("role") == "baked_map_composition"
    ]
    assert composition_assets == ["composition/composition_tiles_v19.zip"], (
        composition_assets
    )
    assert (PORTABLE_ASSETS / composition_assets[0]).is_file()

    sys.path.insert(0, str(GENERATOR))
    from portable_map import validate_portable

    result = validate_portable(PORTABLE, verify_hashes=True)
    assert result["ok"], result["errors"]

    sys.path.insert(0, str(ROOT))
    from versioning import GAME_VERSION

    assert GAME_VERSION == "0.8.1", GAME_VERSION

    print("OPEN NIGHT PASS 19 MAP AUDIT: PASS")
    print("  release: 0.8.1; render pass: 19")
    print("  frozen Pass 18 geometry with 95 converged building assignments")
    print("  32 day + 32 night baked composition tiles")
    print("  runtime, generator mirror and portable map agree")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
