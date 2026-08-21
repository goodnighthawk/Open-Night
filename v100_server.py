from __future__ import annotations

"""Canonical Open Night v1.2 authoritative server entry.

The mature server remains the implementation library for multiplayer, persistence,
chat, vehicles and other gameplay. v1.0 installed the curb-safe GridWorld layout
and 0.5x world normalization; v1.1 additionally derives traffic and pedestrian
routes from that same normalized GridWorld before the simulation starts.
"""

import sys

import v100_runtime_refinement
import v100_safe_layout
v100_safe_layout.install(v100_runtime_refinement)
v100_runtime_refinement.install()
import v100_scale_normalization
v100_scale_normalization.install()

import server
import v110_bug_delivery_server
import v110_bug_railway_relay_server
import v110_grid_population
import v110_job_locations
import v110_pedestrian_flow
import v110_vehicle_proportions
v110_pedestrian_flow.install(v110_grid_population)
v110_vehicle_proportions.install(server)
from gameplay.jump_contract import directional_jump_velocity
from grid_runtime import ground_grid_enabled, load_ground_grid
from versioning import version_label


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
    if world.width != 128 or world.height != 48:
        errors.append(f"grid: expected doubled 128x48 cells, got {world.width}x{world.height}")
    if world.width * world.height != 2 * 64 * 48:
        errors.append("grid: playable map area is not exactly 2x the approved baseline")
    if world.world_w != world.width * world.cell_px:
        errors.append("grid: world_w does not match width * cell_px")
    if world.world_h != world.height * world.cell_px:
        errors.append("grid: world_h does not match height * cell_px")
    try:
        world.choose_spawn("ground", server.PLAYER_RADIUS)
    except Exception as exc:
        errors.append(f"grid: no valid Ground spawn: {exc}")

    if not errors:
        try:
            # Supplier/buyer coordinates are legacy source-world pixels. Scale
            # them onto this exact GridWorld before interaction or map UI uses
            # the shared ACTIVE_MAP object.
            v110_job_locations.normalize(map_config, world, player_radius=server.PLAYER_RADIUS)
            audit = v110_grid_population.prepare_and_initialize(server, map_config, world)
        except Exception as exc:
            errors.append(f"grid population: {exc}")
        else:
            if int(server.TRAFFIC_COUNT) > 0 and int(audit.get("traffic_spawned", 0)) < 1:
                errors.append("grid population: traffic requested but no safe traffic cars spawned")
            if int(audit.get("pedestrians_spawned", 0)) < 1:
                errors.append("grid population: no safe pedestrians spawned")
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
    # Must be installed after Railway's optional GitHub mirror wrapper so a
    # reconnect retry returns the existing DB report instead of creating a
    # duplicate DB row / duplicate GitHub issue. Passing the mature server also
    # adds an early duplicate receipt before its normal 45 s rate-limit checks.
    v110_bug_delivery_server.install(server)
    # Accept a narrow first-frame bug relay command so desktop clients can send
    # reports to Railway even while their gameplay session is local/LAN.
    v110_bug_railway_relay_server.install(server)


def main() -> None:
    install_v100_server()
    # The canonical entrypoint owns the public/default identity as well as the
    # GridWorld runtime. This prevents an old implementation-library constant
    # from leaking back into discovery after a version promotion.
    server.SERVER_NAME = version_label()
    if len(sys.argv) == 1:
        # The retained graphical server-control window historically spawned
        # server.py directly. Patch only that no-argument launcher path so the
        # child also returns through this canonical v1.1 entrypoint.
        import v110_server_launcher_patch
        v110_server_launcher_patch.install()
    server.cli_main()


if __name__ == "__main__":
    main()
