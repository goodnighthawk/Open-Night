from __future__ import annotations

"""Normalize legacy supplier/buyer points onto the v1.1 GridWorld.

The authoritative GridWorld was linearly normalized from 16384x12288 to
8192x6144, but the legacy points.csv job coordinates remained in source-world
pixels.  That left the supplier/customer outside the playable world and therefore
absent from GridWorld map UI and interaction.  Scale once from map metadata to the
actual GridWorld dimensions and snap each destination to walkable Ground.
"""

from typing import Any

JOB_KEYS = ("supplier_pos", "customer_pos")


def _point(raw: Any) -> tuple[float, float] | None:
    try:
        return float(raw[0]), float(raw[1])
    except (TypeError, ValueError, IndexError, KeyError):
        return None


def normalize(map_config: dict, world, *, player_radius: float = 18.0) -> dict[str, list[float]]:
    runtime = map_config.setdefault("runtime", {})
    existing = runtime.get("v110_job_location_normalization")
    if isinstance(existing, dict) and existing.get("applied"):
        return {
            key: list(map_config.get(key, [0.0, 0.0]))
            for key in JOB_KEYS
        }

    try:
        source_w = float(map_config.get("world_w", world.world_w))
        source_h = float(map_config.get("world_h", world.world_h))
    except (TypeError, ValueError):
        source_w, source_h = float(world.world_w), float(world.world_h)
    if source_w <= 0.0 or source_h <= 0.0:
        source_w, source_h = float(world.world_w), float(world.world_h)

    sx = float(world.world_w) / source_w
    sy = float(world.world_h) / source_h
    normalized: dict[str, list[float]] = {}
    source_points: dict[str, list[float]] = {}

    for key in JOB_KEYS:
        parsed = _point(map_config.get(key))
        if parsed is None:
            parsed = (float(world.world_w) * 0.5, float(world.world_h) * 0.5)
        source_points[key] = [parsed[0], parsed[1]]
        x = max(0.0, min(float(world.world_w), parsed[0] * sx))
        y = max(0.0, min(float(world.world_h), parsed[1] * sy))
        # Job NPCs must stand on pavement, never as floating areas in traffic.
        sidewalk_cells = [
            world.cell_center(gx, gy)
            for gy in range(world.height) for gx in range(world.width)
            if world.collision_at("ground", *world.cell_center(gx, gy)) in {"walk", "sidewalk"}
        ]
        if sidewalk_cells:
            x, y = min(sidewalk_cells, key=lambda point: (point[0] - x) ** 2 + (point[1] - y) ** 2)
        map_config[key] = [round(float(x), 3), round(float(y), 3)]
        normalized[key] = list(map_config[key])

    runtime["v110_job_location_normalization"] = {
        "applied": True,
        "source_world_size": [source_w, source_h],
        "grid_world_size": [float(world.world_w), float(world.world_h)],
        "scale": [sx, sy],
        "source_points": source_points,
        "normalized_points": normalized,
        "authority": "gridworld_ground_walkable",
    }
    _install_grid_traffic_signals(map_config, world)
    return normalized


def _install_grid_traffic_signals(map_config: dict, world) -> None:
    """Restore synchronized signals at GridWorld road intersections."""
    if map_config.get("traffic_signals"):
        return
    try:
        from v110_pedestrian_connectivity import road_bands
        horizontal, vertical = road_bands(world)
    except Exception:
        return
    signals = []
    for row_index, row in enumerate(horizontal):
        for col_index, col in enumerate(vertical):
            corners = (
                ("nw", col.start - 1, row.start - 1, 0),
                ("se", col.end + 1, row.end + 1, 0),
                ("ne", col.end + 1, row.start - 1, 1),
                ("sw", col.start - 1, row.end + 1, 1),
            )
            for arm, gx, gy, phase in corners:
                cx, cy = world.cell_center(gx, gy)
                signals.append({"id": f"grid_signal_{row_index:02d}_{col_index:02d}_{arm}",
                                "pos": [round(cx, 3), round(cy, 3)],
                                "phase": phase, "orientation": arm, "grid_native": True})
    map_config["traffic_signals"] = signals
    map_config.setdefault("runtime", {})["grid_traffic_signal_count"] = len(signals)


def install_client(game_client) -> None:
    game = game_client.Game
    if bool(getattr(game, "_v110_job_locations_installed", False)):
        return
    original_init = game.__init__

    def init_v110(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        world = getattr(self, "grid_world", None)
        if world is not None:
            normalize(self.map_config, world, player_radius=getattr(game_client, "PLAYER_RADIUS", 18.0))
            # Job markers are part of dynamic UI; invalidate any pre-normalization
            # world-map cache created by another wrapper during startup.
            self._world_map_cache = None
            self._world_map_cache_key = None

    game.__init__ = init_v110
    game._v110_job_locations_installed = True
