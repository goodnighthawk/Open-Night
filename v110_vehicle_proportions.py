from __future__ import annotations

"""v1.1 vehicle proportions matched to the normalized GridWorld/player scale.

GridWorld Ground renders the player at a 2x minimum scale, so the previous v1.1
sedan target (~83 px long) still read as a toy beside a roughly 58 px tall player.
This module scales the authoritative vehicle metadata so a normal sedan is about
2.6 player-heights long while keeping its collision body synchronized with the
visible sprite. The mature vehicle catalog remains the source of relative class
sizes: vans, buses, limos and trucks still scale from their authored proportions.

The same install point also activates the bounded v1.1 GridWorld traffic recovery
watchdog so every runtime path (server and proof harness) uses identical vehicle
proportions, lane separation and deadlock handling.
"""

import v110_traffic_recovery

# A 48 px legacy sedan becomes ~110 px of server render metadata and ~152 px on
# the client after draw_vehicle's retained 1.38 multiplier. Against the ~58 px
# GridWorld player this is ~2.62:1 instead of the old ~1.43:1 toy-car ratio.
RENDER_META_SCALE = 2.30
COLLISION_LENGTH_META_SCALE = 2.61
COLLISION_WIDTH_META_SCALE = 3.00
CLIENT_RENDER_MULTIPLIER = 1.38
GROUND_PLAYER_TARGET_HEIGHT_PX = 58.0
MIN_SEDAN_TO_PLAYER_LENGTH_RATIO = 2.50
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
        # Recovery is independently idempotent; keep it installed even if another
        # harness applied the metadata patch first.
        v110_traffic_recovery.install(server_module)
        return
    original = server_module._traffic_asset

    def traffic_asset_v110(index: int) -> dict:
        return scaled_meta(original(index))

    server_module._v110_original_traffic_asset = original
    server_module._traffic_asset = traffic_asset_v110
    server_module._v110_vehicle_proportions_installed = True
    v110_traffic_recovery.install(server_module)
