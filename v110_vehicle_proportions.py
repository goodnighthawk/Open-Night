from __future__ import annotations

"""v1.1 vehicle proportions matched to the normalized GridWorld/player scale.

The earlier v1.1 correction was still visually too conservative in actual gameplay:
vehicles were technically larger than legacy traffic but continued to read as toys
against the broad GridWorld roads and buildings.  This pass makes an ordinary sedan
roughly 3.4 player-heights long on screen, while preserving the authored relative
sizes of vans, buses, limos and trucks.

Collision growth is intentionally smaller than visual growth.  The traffic solver
therefore keeps enough intersection clearance while the sprite finally has the
visual mass expected of a car.  The recovery watchdog remains installed from the
same authoritative metadata hook.
"""

import v110_traffic_recovery

# A 48 px legacy sedan becomes ~144 px of server render metadata and ~199 px on
# the client after draw_vehicle's retained 1.38 multiplier. Against the ~58 px
# GridWorld player this is ~3.43:1, giving cars readable real-world visual mass.
RENDER_META_SCALE = 3.00
# Collision envelopes remain smaller than the visible sprite so the larger visual
# treatment does not consume the full three-cell road/intersection clearance.
COLLISION_LENGTH_META_SCALE = 2.65
COLLISION_WIDTH_META_SCALE = 2.75
CLIENT_RENDER_MULTIPLIER = 1.38
GROUND_PLAYER_TARGET_HEIGHT_PX = 58.0
MIN_SEDAN_TO_PLAYER_LENGTH_RATIO = 3.25
MIN_EXPECTED_SEDAN_LENGTH_PX = GROUND_PLAYER_TARGET_HEIGHT_PX * MIN_SEDAN_TO_PLAYER_LENGTH_RATIO


def scaled_meta(meta: dict) -> dict:
    out = dict(meta)
    out["render_length"] = max(48, int(round(float(out.get("render_length", 48)) * RENDER_META_SCALE)))
    out["collision_length"] = max(44.0, float(out.get("collision_length", 42.0)) * COLLISION_LENGTH_META_SCALE)
    out["collision_width"] = max(24.0, float(out.get("collision_width", 18.0)) * COLLISION_WIDTH_META_SCALE)
    out["v110_vehicle_proportions"] = True
    return out


def expected_client_render_length(server_render_length: float) -> float:
    """Mirror client.draw_vehicle's current target-length contract for audits."""
    return max(62.0, float(server_render_length) * CLIENT_RENDER_MULTIPLIER)


def expected_sedan_to_player_ratio(server_render_length: float, player_height_px: float = GROUND_PLAYER_TARGET_HEIGHT_PX) -> float:
    return expected_client_render_length(server_render_length) / max(1.0, float(player_height_px))


def install(server_module) -> None:
    if bool(getattr(server_module, "_v110_vehicle_proportions_installed", False)):
        v110_traffic_recovery.install(server_module)
        return
    original = server_module._traffic_asset

    def traffic_asset_v110(index: int) -> dict:
        return scaled_meta(original(index))

    server_module._v110_original_traffic_asset = original
    server_module._traffic_asset = traffic_asset_v110
    server_module._v110_vehicle_proportions_installed = True
    v110_traffic_recovery.install(server_module)
