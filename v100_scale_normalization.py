from __future__ import annotations

"""Shared 0.5x linear normalization for the v1.0 authoritative GridWorld.

The city art/grid was authored at 256 px per logical cell, which made roads,
blocks and buildings approximately twice too large relative to the existing
player/vehicle sprites. This pass keeps the 64x48 logical topology unchanged but
renormalizes world-space to 128 px per cell. Collision, rendering, object anchors,
light pools and network metadata all continue to derive from the same GridWorld.
"""

from dataclasses import replace
from functools import lru_cache

WORLD_LINEAR_SCALE = 0.5
TARGET_CELL_PX = 128
_INSTALLED = False
_PIXEL_FIELDS = (
    "offset_x_px", "offset_y_px", "width_px", "height_px",
    "light_offset_x_px", "light_offset_y_px", "light_radius_px",
    "collision_radius_px",
)


def _scaled_int(value, scale: float, *, minimum: int | None = None) -> int:
    result = int(round(float(value) * scale))
    return result if minimum is None else max(minimum, result)


def apply_world_scale(world):
    if getattr(world, "_v100_world_scale_normalized", False):
        return world
    old_cell = int(world.cell_px)
    if old_cell == TARGET_CELL_PX:
        world._v100_world_scale_normalized = True
        return world
    if old_cell <= 0:
        raise RuntimeError(f"invalid GridWorld cell size {old_cell}")
    scale = TARGET_CELL_PX / float(old_cell)

    # Scale all pixel-local object dimensions/offsets while retaining logical
    # grid anchors. This keeps lamps, fire escapes, markings and roof equipment
    # registered to the same collision cells after the world becomes smaller.
    for item in world.objects:
        for key in _PIXEL_FIELDS:
            if key in item:
                # Offsets are signed coordinates. Clamping negative values to zero
                # detached north/west lamp heads from their bases and shifted the
                # outer lane dividers onto one side of the road.
                minimum = 1 if key in {"width_px", "height_px", "light_radius_px"} else None
                item[key] = _scaled_int(item[key], scale, minimum=minimum)

    # Objects without explicit dimensions inherit catalog-native size, so scale
    # those definitions too. ObjectDef is frozen; replace entries atomically.
    for object_id, definition in list(world.catalog.objects.items()):
        world.catalog.objects[object_id] = replace(
            definition,
            native_width_px=_scaled_int(definition.native_width_px, scale, minimum=1),
            native_height_px=_scaled_int(definition.native_height_px, scale, minimum=1),
        )

    # Login spawns are world-space coordinates rather than cells.
    scaled_spawns = []
    for raw in world.login_spawns:
        try:
            scaled_spawns.append([float(raw[0]) * scale, float(raw[1]) * scale])
        except (TypeError, ValueError, IndexError):
            scaled_spawns.append(raw)
    world.login_spawns = scaled_spawns
    world.data["login_spawns"] = scaled_spawns

    world.cell_px = TARGET_CELL_PX
    world.world_w = world.width * world.cell_px
    world.world_h = world.height * world.cell_px
    world.data["cell_px"] = TARGET_CELL_PX
    world.data["world_w"] = world.world_w
    world.data["world_h"] = world.world_h
    world.data.setdefault("runtime_refinement", {}).update({
        "world_linear_scale": WORLD_LINEAR_SCALE,
        "source_cell_px": old_cell,
        "normalized_cell_px": TARGET_CELL_PX,
        "normalized_world_size": [world.world_w, world.world_h],
        "scale_authority": "shared_gridworld_collision_render_network",
    })
    # Object collision circles are expressed in the pixel-local fields scaled
    # above. Discard any pre-normalization cache so the next query rebuilds it
    # from the normalized radii and anchors.
    for cache_key in ("_object_collision_cache", "_object_collision_cache_count"):
        if hasattr(world, cache_key):
            delattr(world, cache_key)
    world._v100_world_scale_normalized = True
    return world


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    import grid_runtime
    original = grid_runtime.load_ground_grid

    @lru_cache(maxsize=1)
    def scaled_loader():
        return apply_world_scale(original())

    grid_runtime.load_ground_grid = scaled_loader
    _INSTALLED = True
