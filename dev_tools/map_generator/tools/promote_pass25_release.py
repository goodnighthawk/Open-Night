from __future__ import annotations

"""Promote the frozen Pass 25 visual candidate into the sole runtime map.

This script is deliberately a release wrapper around the older promotion code: it
first rebuilds and audits Pass 25, then reuses the established runtime geometry
writer while replacing every stale Pass 19 release identifier.  It does not alter
Pass 25 artwork.
"""

import csv
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import build_pass25_visual_convergence as pass25
import promote_unified_composition as legacy

ROOT = Path(__file__).resolve().parents[3]
VERSION = "0.8.2"
PASS = 25
BUILD_ID = "open_night_v0_8_2_pass25_default_only"
ARCHIVE_REL = "assets/environment/approved/map_001_gwb_corridor/composition_tiles_v25.zip"
ARCHIVE = ROOT / ARCHIVE_REL
_LEGACY_MAP_ROWS = legacy.map_rows


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, fields: tuple[str, ...], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader(); writer.writerows(rows)


def map_rows() -> list[dict[str, str]]:
    rows = _LEGACY_MAP_ROWS()
    values = {row["key"]: dict(row) for row in rows}
    replacements = {
        "description": "Pass 25 final visual-convergence corridor: fixed-scale modular buildings, street detail and hand-authored landmarks; the default and only playable map.",
        "baked_composition_archive": ARCHIVE_REL,
        "map_build_id": BUILD_ID,
        "render_pass": str(PASS),
        "building_cosmetic_rule": "pass25_fixed_scale_modular_massing_landmark_v1",
        "building_sprite_scale_band": "0.88..1.12",
    }
    for key, value in replacements.items():
        values[key]["value"] = value
    extras = (
        ("building_component_scale_contract", "config/environment_component_scale.csv", "str"),
        ("building_modular_detail_pass", "true", "bool"),
        ("building_massing_convergence_pass", "true", "bool"),
        ("street_detail_density_pass", "true", "bool"),
        ("hand_authored_landmark_pass", "true", "bool"),
        ("final_visual_convergence_pass", "true", "bool"),
        ("visual_convergence_failures", "0", "int"),
        ("approved_visual_checkpoint", "pass25", "str"),
    )
    for key, value, typ in extras:
        values[key] = {"key": key, "value": value, "type": typ}
    order = [row["key"] for row in rows] + [key for key, _, _ in extras]
    return [values[key] for key in order]


def rewrite_render_contract(folder: Path) -> None:
    write_csv(folder / "render_contract.csv", ("key", "value", "type"), [
        {"key": "camera_projection", "value": "orthographic_topdown", "type": "str"},
        {"key": "outdoor_perspective_skew", "value": "0", "type": "float"},
        {"key": "baked_composition", "value": "true", "type": "bool"},
        {"key": "render_pass", "value": str(PASS), "type": "int"},
        {"key": "approved_visual_checkpoint", "value": "pass25", "type": "str"},
    ])


def copy_pass25_semantics(folder: Path) -> None:
    semantic = legacy.SEMANTIC
    for name in (
        "building_component_scale_audit.csv",
        "building_frontage_audit.csv",
        "building_modules.csv",
        "building_module_signatures.csv",
        "building_modular_massing.csv",
        "street_detail_pass23.csv",
        "landmarks_pass24.csv",
    ):
        src = semantic / name
        if src.exists():
            shutil.copy2(src, folder / name)


def rewrite_landmarks(folder: Path) -> None:
    rows = [
        {"id": "gwb", "name": "George Washington Bridge", "kind": "bridge", "x": 7680, "y": 6144},
        {"id": "fort_lee", "name": "Fort Lee", "kind": "district", "x": 2400, "y": 5600},
        {"id": "washington_heights", "name": "Washington Heights", "kind": "district", "x": 13200, "y": 5600},
    ]
    for row in read_csv(legacy.SEMANTIC / "landmarks_pass24.csv"):
        role = str(row.get("visual_role", "landmark"))
        rows.append({
            "id": row["landmark_id"],
            "name": role.replace("_", " ").title(),
            "kind": row["kind"],
            "x": round(float(row["x"]) + float(row["w"]) * .5, 2),
            "y": round(float(row["y"]) + float(row["h"]) * .5, 2),
        })
    write_csv(folder / "landmarks.csv", ("id", "name", "kind", "x", "y"), rows)


def write_release_identity() -> None:
    (ROOT / "VERSION.txt").write_text(
        "Open Night v0.8.2 - Pass 25 final map visual convergence\n",
        encoding="utf-8",
    )
    (ROOT / "versioning.py").write_text(
        '"""Single source of truth for the multiplayer wire/build version."""\n\n'
        'GAME_VERSION = "0.8.2"\n\n\n'
        'def version_label() -> str:\n'
        '    return f"Open Night v{GAME_VERSION}"\n',
        encoding="utf-8",
    )
    (ROOT / "RELEASE_NOTES_OPEN_NIGHT_v0.8.2.md").write_text(
        "# Open Night v0.8.2 — Pass 25 final map convergence\n\n"
        "- Promotes the reviewed Pass 25 Fort Lee → George Washington Bridge → Washington Heights corridor as the default and only playable map.\n"
        "- Locks building component scale to 0.88–1.12 and uses modular roof/facade detail with deterministic anti-repetition signatures.\n"
        "- Adds irregular L/U/stepped/courtyard/chamfered building massing, 501 deterministic street details, and 12 recognizable landmark groups.\n"
        "- Preserves 38 roads, 157 segments, 96 angled segments, 23 T-junctions, 242 compact crossings, Hudson/park geometry, and 95 road-safe buildings.\n"
        "- Ships reviewed day/night Pass 25 baked composition tiles in composition_tiles_v25.zip.\n",
        encoding="utf-8",
    )


def main() -> None:
    pass25.main()
    legacy.ART_ARCHIVE = ARCHIVE
    legacy.map_rows = map_rows
    legacy.main()
    for folder in legacy.MAP_DIRS:
        rewrite_render_contract(folder)
        copy_pass25_semantics(folder)
        rewrite_landmarks(folder)
    write_release_identity()
    print(
        f"PASS25_RELEASE_PROMOTED version={VERSION} pass={PASS} build={BUILD_ID} "
        f"archive={ARCHIVE.name} archive_bytes={ARCHIVE.stat().st_size} maps={len(legacy.MAP_DIRS)}"
    )


if __name__ == "__main__":
    main()
