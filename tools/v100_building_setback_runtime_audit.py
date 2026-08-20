#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from pathlib import Path
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pygame
import v100_runtime_refinement
import v100_safe_layout

v100_safe_layout.install(v100_runtime_refinement)
v100_runtime_refinement.install()

from grid_renderer import GridRenderer
from grid_runtime import load_ground_grid

OUT = ROOT / "assets" / "grid_v100" / "BUILDING_SETBACK_RUNTIME_AUDIT.json"


def main() -> None:
    pygame.init()
    pygame.display.set_mode((1, 1))
    world = load_ground_grid()
    buildings = list(world.data["building_synthesis"]["buildings"])
    footprints = {
        str(building["building_id"]): v100_runtime_refinement._footprint(building)
        for building in buildings
    }

    overlap_cells: set[tuple[int, int]] = set()
    adjacent_pairs: list[list[str]] = []
    building_ids = sorted(footprints)
    for index, building_id in enumerate(building_ids):
        cells = footprints[building_id]
        neighbours = {
            (x + dx, y + dy)
            for x, y in cells
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))
        }
        for other_id in building_ids[index + 1:]:
            overlap_cells.update(cells & footprints[other_id])
            if neighbours & footprints[other_id]:
                adjacent_pairs.append([building_id, other_id])

    ground = world.layers["ground"]
    roof = world.layers["roof"]
    theme_mismatches = []
    roof_mismatches = []
    for building in buildings:
        building_id = str(building["building_id"])
        expected_prefix = f"bld_{building['theme']}_"
        for gx, gy in footprints[building_id]:
            if not ground[gy][gx].startswith(expected_prefix):
                theme_mismatches.append([building_id, gx, gy, ground[gy][gx]])
            if roof[gy][gx] != ground[gy][gx]:
                roof_mismatches.append([building_id, gx, gy, ground[gy][gx], roof[gy][gx]])

    renderer = GridRenderer(world)
    edge_tile_ids = sorted({
        ground[gy][gx]
        for cells in footprints.values()
        for gx, gy in cells
        if not ground[gy][gx].endswith("_fill")
    })
    alpha_rows = []
    for tile_id in edge_tile_ids:
        image = renderer._tile_surface(tile_id)
        area = image.get_width() * image.get_height()
        fully_opaque = pygame.mask.from_surface(image, threshold=254).count()
        alpha_rows.append({
            "tile_id": tile_id,
            "area_px": area,
            "transparent_or_translucent_px": area - fully_opaque,
        })

    refinement = dict(world.data.get("runtime_refinement") or {})
    errors = []
    if overlap_cells:
        errors.append(f"building overlap cells: {sorted(overlap_cells)[:12]}")
    if adjacent_pairs:
        errors.append(f"building pairs lost one-cell setback: {adjacent_pairs[:12]}")
    if theme_mismatches:
        errors.append(f"building theme ownership mismatches: {theme_mismatches[:12]}")
    if roof_mismatches:
        errors.append(f"Ground/Roof registration mismatches: {roof_mismatches[:12]}")
    opaque_edges = [row["tile_id"] for row in alpha_rows if row["transparent_or_translucent_px"] <= 0]
    if opaque_edges:
        errors.append(f"building edge alpha was erased: {opaque_edges[:12]}")
    if refinement.get("building_edge_alpha_policy") != "source_alpha_preserved_exterior_frame_removed":
        errors.append(f"unexpected edge policy: {refinement}")

    audit = {
        "proof": "canonical_v100_joint_building_setback_and_alpha",
        "building_count": len(buildings),
        "shifted_building_count": int(refinement.get("centered_building_count", 0)),
        "building_overlap_cell_count": len(overlap_cells),
        "building_adjacent_pair_count": len(adjacent_pairs),
        "minimum_building_setback_cells": 1,
        "theme_ownership_mismatch_count": len(theme_mismatches),
        "ground_roof_registration_mismatch_count": len(roof_mismatches),
        "edge_tile_count": len(alpha_rows),
        "edge_tiles_with_preserved_alpha": sum(row["transparent_or_translucent_px"] > 0 for row in alpha_rows),
        "minimum_edge_transparent_or_translucent_px": min(
            (row["transparent_or_translucent_px"] for row in alpha_rows), default=0
        ),
        "edge_alpha_policy": refinement.get("building_edge_alpha_policy"),
        "edge_alpha_rows": alpha_rows,
        "errors": errors,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(audit, indent=2, sort_keys=True))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
