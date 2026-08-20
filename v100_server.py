from __future__ import annotations

"""Canonical Open Night v1.0 authoritative server entry.

The mature server remains the implementation library for multiplayer, persistence,
chat, vehicles and other gameplay. v1.0 installs the curb-safe GridWorld layout
and 0.5x world normalization before importing the server so authoritative
collision and network metadata use the same 128 px logical cell scale.
"""

import v100_runtime_refinement
import v100_safe_layout
v100_safe_layout.install(v100_runtime_refinement)
v100_runtime_refinement.install()
import v100_scale_normalization
v100_scale_normalization.install()

import server
from gameplay.jump_contract import directional_jump_velocity
from grid_runtime import ground_grid_enabled, load_ground_grid


_legacy_validate_map = server.validate_map
_legacy_request_player_jump = server.request_player_jump


def validate_active_authority(map_config: dict) -> list[str]:
    if not ground_grid_enabled(map_config):
        return _legacy_validate_map(map_config)

    world = load_ground_grid()
    errors: list[str] = []
    if world.cell_px != v100_scale_normalization.TARGET_CELL_PX:
        errors.append(
            f"grid: expected {v100_scale_normalization.TARGET_CELL_PX}px normalized cells, got {world.cell_px}"
        )
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


def request_player_jump_v100(session, now: float | None = None) -> str:
    """Directional jump only when movement is held on the Space input frame."""
    result = _legacy_request_player_jump(session, now)
    if result not in {"jump", "double_jump"}:
        return result
    speed = server.DOUBLE_JUMP_FORWARD_SPEED if result == "double_jump" else server.JUMP_FORWARD_SPEED
    session.jump_velocity_x, session.jump_velocity_y = directional_jump_velocity(
        session.input_x, session.input_y, speed
    )
    return result


def install_v100_server() -> None:
    server.validate_map = validate_active_authority
    server.request_player_jump = request_player_jump_v100


def main() -> None:
    install_v100_server()
    server.cli_main()


if __name__ == "__main__":
    main()
