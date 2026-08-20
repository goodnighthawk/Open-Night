from __future__ import annotations

"""v1.1 vehicle proportions matched to the normalized GridWorld/player scale.

The approved vehicle manifest predates the 128 px GridWorld normalization. The
client already enlarged the old render_length, but the authoritative collision
body remained much smaller, so cars looked undersized and their visible sprites
could overlap before avoidance/collision engaged. Scale the catalog metadata at
the server boundary so rendering and physics remain synchronized without rewriting
the shared art manifest.

The same install point also activates the bounded v1.1 GridWorld traffic recovery
watchdog so every runtime path (server and proof harness) uses identical vehicle
proportions, lane separation and deadlock handling.
"""

import v110_traffic_recovery

RENDER_META_SCALE = 1.25
COLLISION_LENGTH_META_SCALE = 1.42
COLLISION_WIDTH_META_SCALE = 1.45
CLIENT_RENDER_MULTIPLIER = 1.38


def scaled_meta(meta: dict) -> dict:
    out = dict(meta)
    out["render_length"] = max(30, int(round(float(out.get("render_length", 48)) * RENDER_META_SCALE)))
    out["collision_length"] = max(24.0, float(out.get("collision_length", 42.0)) * COLLISION_LENGTH_META_SCALE)
    out["collision_width"] = max(14.0, float(out.get("collision_width", 18.0)) * COLLISION_WIDTH_META_SCALE)
    out["v110_vehicle_proportions"] = True
    return out


def expected_client_render_length(server_render_length: float) -> float:
    """Mirror client.draw_vehicle's current target-length contract for audits."""
    return max(62.0, float(server_render_length) * CLIENT_RENDER_MULTIPLIER)


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
