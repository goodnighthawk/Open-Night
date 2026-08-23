from __future__ import annotations

"""Normalize legacy supplier/buyer points onto the v2.8 GridWorld rooftops.

The authoritative GridWorld was linearly normalized from 16384x12288 to
8192x6144, but the legacy points.csv job coordinates remained in source-world
pixels.  That left the supplier/customer outside the playable world and therefore
absent from GridWorld map UI and interaction.  Scale once from map metadata to the
actual GridWorld dimensions and distribute each destination over an accessible
building roof.
"""

from typing import Any

from building_morphology import footprint_for

JOB_KEYS = ("supplier_pos", "customer_pos")
JOB_NPC_COUNT = 20


def _point(raw: Any) -> tuple[float, float] | None:
    try:
        return float(raw[0]), float(raw[1])
    except (TypeError, ValueError, IndexError, KeyError):
        return None


def _roof_candidates(world, player_radius: float) -> list[dict]:
    """Return one safe central roof position per authoritative building."""
    buildings = sorted(
        list((world.data.get("building_synthesis") or {}).get("buildings") or []),
        key=lambda row: str(row.get("building_id", "")),
    )
    candidates: list[dict] = []
    for building in buildings:
        try:
            rect = tuple(map(int, building["rect"]))
            cells = footprint_for(rect, building.get("notch"))
        except (KeyError, TypeError, ValueError):
            continue
        center_x = (rect[0] + rect[2]) * 0.5
        center_y = (rect[1] + rect[3]) * 0.5
        usable = []
        for gx, gy in cells:
            x, y = world.cell_center(gx, gy)
            if world.circle_roof_walkable(x, y, player_radius):
                usable.append(((gx - center_x) ** 2 + (gy - center_y) ** 2, gy, gx, x, y))
        if not usable:
            continue
        _distance, _gy, _gx, x, y = min(usable)
        candidates.append({
            "building_id": str(building.get("building_id", "")),
            "pos": (float(x), float(y)),
        })
    return candidates


def normalize(map_config: dict, world, *, player_radius: float = 18.0) -> dict[str, list[float]]:
    runtime = map_config.setdefault("runtime", {})
    existing = runtime.get("v110_job_location_normalization")
    if (isinstance(existing, dict) and existing.get("applied")
            and existing.get("authority") == "gridworld_rooftop_v28"
            and len(map_config.get("job_locations", [])) >= JOB_NPC_COUNT):
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
    scaled_targets: dict[str, tuple[float, float]] = {}
    for key in JOB_KEYS:
        parsed = _point(map_config.get(key))
        if parsed is None:
            parsed = (float(world.world_w) * 0.5, float(world.world_h) * 0.5)
        source_points[key] = [parsed[0], parsed[1]]
        x = max(0.0, min(float(world.world_w), parsed[0] * sx))
        y = max(0.0, min(float(world.world_h), parsed[1] * sy))
        scaled_targets[key] = (x, y)

    # Reports #187/#191 require every supplier and buyer to be a true roof
    # occupant. Seed the legacy pair on their nearest roofs, then use
    # deterministic farthest-point sampling to spread the remaining jobs over
    # distinct accessible buildings.
    candidates = _roof_candidates(world, max(1.0, float(player_radius)))
    if len(candidates) < JOB_NPC_COUNT:
        raise RuntimeError(
            f"v2.8 rooftop job placement requires {JOB_NPC_COUNT} accessible roofs; found {len(candidates)}"
        )
    remaining = list(candidates)
    selected: list[dict] = []
    for key in JOB_KEYS:
        target = scaled_targets[key]
        choice = min(
            remaining,
            key=lambda candidate: (
                (candidate["pos"][0] - target[0]) ** 2 + (candidate["pos"][1] - target[1]) ** 2,
                candidate["building_id"],
            ),
        )
        selected.append(choice)
        remaining.remove(choice)
    while remaining and len(selected) < JOB_NPC_COUNT:
        choice = max(
            remaining,
            key=lambda candidate: (
                min(
                    (candidate["pos"][0] - used["pos"][0]) ** 2
                    + (candidate["pos"][1] - used["pos"][1]) ** 2
                    for used in selected
                ),
                candidate["building_id"],
            ),
        )
        selected.append(choice)
        remaining.remove(choice)

    map_config["supplier_pos"] = [round(value, 3) for value in selected[0]["pos"]]
    map_config["customer_pos"] = [round(value, 3) for value in selected[1]["pos"]]
    normalized = {key: list(map_config[key]) for key in JOB_KEYS}
    roles = ["supplier", "buyer"] * (JOB_NPC_COUNT // 2)
    map_config["job_locations"] = [
        {
            "id": f"job_{role}_{index // 2 + 1:02d}",
            "role": role,
            "pos": [round(float(candidate["pos"][0]), 3), round(float(candidate["pos"][1]), 3)],
            "level": 1,
            "building_id": candidate["building_id"],
            "placement_policy": "accessible_roof_center_v28",
            "appearance_index": 40 + index,
            "authoritative_npc": True,
        }
        for index, (role, candidate) in enumerate(zip(roles, selected))
    ]

    runtime["v110_job_location_normalization"] = {
        "applied": True,
        "source_world_size": [source_w, source_h],
        "grid_world_size": [float(world.world_w), float(world.world_h)],
        "scale": [sx, sy],
        "source_points": source_points,
        "normalized_points": normalized,
        "authority": "gridworld_rooftop_v28",
        "job_npc_count": len(map_config["job_locations"]),
        "job_roles": {role: roles.count(role) for role in set(roles)},
        "distinct_rooftop_buildings": len({row["building_id"] for row in map_config["job_locations"]}),
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
