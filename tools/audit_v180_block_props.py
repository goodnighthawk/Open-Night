from __future__ import annotations

from pathlib import Path
import sys

import pygame


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from grid_runtime import load_ground_grid
from procedural_block_props import ROOF_PROPS, STREET_PROPS


def main() -> int:
    pygame.init()
    asset_dir = ROOT / "assets" / "source_packs" / "block_props"
    files = sorted(asset_dir.glob("*.png"))
    assert len(files) == 15, len(files)
    for path in files:
        image = pygame.image.load(path)
        assert image.get_flags() & pygame.SRCALPHA, path.name
        width, height = image.get_size()
        corners = ((0, 0), (width - 1, 0), (0, height - 1), (width - 1, height - 1))
        assert all(image.get_at(point).a == 0 for point in corners), path.name
        assert pygame.mask.from_surface(image, 254).count() > 0, f"{path.name} has no opaque artwork"

    world = load_ground_grid()
    objects = [item for item in world.objects if item.get("procedural_block_prop")]
    expected_assets = {item[0] for item in ROOF_PROPS + STREET_PROPS}
    assert {str(item["asset"]) for item in objects} == expected_assets
    assert len(objects) == 84, len(objects)
    assert sum(item.get("placement_zone") == "roof" for item in objects) == 28
    assert sum(item.get("placement_zone") == "block_edge" for item in objects) == 56
    for item in objects:
        assert world.in_bounds(int(item["gx"]), int(item["gy"]))
        if item.get("placement_zone") == "block_edge":
            tile_id = world.tile_id("ground", int(item["gx"]), int(item["gy"]))
            assert tile_id.startswith(("pavement", "curb_")), (item["id"], tile_id)

    print("OPEN NIGHT v1.8 PROCEDURAL BLOCK PROPS AUDIT: PASS")
    print("  15 transparent assets; 28 roof + 56 block-edge placements; all asset types used")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
