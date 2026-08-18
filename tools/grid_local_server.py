from __future__ import annotations

"""Quick-test server entry point for the v1.0 grid-authoritative exterior.

The legacy map configuration remains available as migration/reference data, but its
vector-road validator must not prevent the active Ground GridWorld from booting.
This wrapper proves the authoritative grid can load, then delegates to the normal
server while suppressing only the obsolete legacy-map validation for maps whose
runtime authority is the v1.0 Ground grid.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import server
from grid_runtime import ground_grid_enabled, load_ground_grid


_legacy_validate_map = server.validate_map


def _validate_active_authority(map_config: dict) -> list[str]:
    if not ground_grid_enabled(map_config):
        return _legacy_validate_map(map_config)

    # Loading GridWorld performs the grid-format/catalog checks used by the real
    # renderer/collision runtime. Keep a few contract assertions here so Quick
    # Test fails loudly if the authoritative playable world itself is malformed.
    world = load_ground_grid()
    errors: list[str] = []
    if world.cell_px != 256:
        errors.append(f"grid: expected 256px cells, got {world.cell_px}")
    if world.width != 64 or world.height != 48:
        errors.append(f"grid: expected 64x48 cells, got {world.width}x{world.height}")
    if world.world_w != world.width * world.cell_px:
        errors.append("grid: world_w does not match width * cell_px")
    if world.world_h != world.height * world.cell_px:
        errors.append("grid: world_h does not match height * cell_px")
    try:
        world.choose_spawn("ground", server.PLAYER_RADIUS)
    except Exception as exc:
        errors.append(f"grid: no valid Ground spawn: {exc}")
    return errors


def main() -> None:
    server.validate_map = _validate_active_authority
    server.cli_main()


if __name__ == "__main__":
    main()
