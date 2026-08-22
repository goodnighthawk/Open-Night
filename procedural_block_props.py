from __future__ import annotations

from typing import Any


ROOF_PROPS = (
    ("block_prop_roof_fan_red", 86, 125),
    ("block_prop_roof_vent_round", 82, 98),
    ("block_prop_roof_hvac_blue", 150, 144),
)

STREET_PROPS = (
    ("block_prop_dumpster_green", 220, 127),
    ("block_prop_planter_gold_shrubs", 156, 142),
    ("block_prop_recycling_round", 112, 110),
    ("block_prop_planter_gold_long_soil", 76, 195),
    ("block_prop_patio_umbrella", 184, 140),
    ("block_prop_planter_gold_square_soil", 150, 145),
    ("block_prop_shrub_round", 166, 178),
    ("block_prop_planter_gold_long_hedge", 72, 193),
    ("block_prop_planter_wood_square_soil", 150, 145),
    ("block_prop_planter_wood_shrubs", 156, 141),
    ("block_prop_planter_gold_long_hedge_alt", 70, 196),
    ("block_prop_planter_wood_long_soil", 76, 191),
)


def _sidewalk_candidates(rows: list[list[str]], rect: list[int]) -> list[tuple[int, int]]:
    left, top, right, bottom = map(int, rect)
    candidates: list[tuple[int, int]] = []
    for gx in range(left - 1, right + 2):
        candidates.extend(((gx, top - 1), (gx, bottom + 1)))
    for gy in range(top, bottom + 1):
        candidates.extend(((left - 1, gy), (right + 1, gy)))
    height = len(rows)
    width = len(rows[0]) if rows else 0
    return [
        (gx, gy) for gx, gy in candidates
        if 0 <= gx < width and 0 <= gy < height
        and rows[gy][gx].startswith(("pavement", "curb_"))
    ]


def build_procedural_block_props(
    rows: list[list[str]], buildings: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Place the submitted prop set deterministically across building blocks."""
    objects: list[dict[str, Any]] = []
    for index, building in enumerate(buildings):
        building_id = str(building["building_id"])
        left, top, right, bottom = map(int, building["rect"])
        roof_asset, roof_w, roof_h = ROOF_PROPS[index % len(ROOF_PROPS)]
        roof_gx = (left + right) // 2
        roof_gy = (top + bottom) // 2
        objects.append({
            "id": f"procedural_{building_id}_roof_prop",
            "asset": roof_asset,
            "gx": roof_gx,
            "gy": roof_gy,
            "offset_x_px": (256 - roof_w) // 2,
            "offset_y_px": (256 - roof_h) // 2,
            "width_px": roof_w,
            "height_px": roof_h,
            "building_id": building_id,
            "procedural_block_prop": True,
            "placement_zone": "roof",
        })
        candidates = _sidewalk_candidates(rows, building["rect"])
        if not candidates:
            continue
        for local_index in range(2):
            asset, width, height = STREET_PROPS[(index * 2 + local_index) % len(STREET_PROPS)]
            pick = (index * 7 + local_index * max(1, len(candidates) // 2)) % len(candidates)
            gx, gy = candidates[pick]
            objects.append({
                "id": f"procedural_{building_id}_street_prop_{local_index + 1}",
                "asset": asset,
                "gx": gx,
                "gy": gy,
                "offset_x_px": (256 - width) // 2,
                "offset_y_px": (256 - height) // 2,
                "width_px": width,
                "height_px": height,
                "building_id": building_id,
                "procedural_block_prop": True,
                "placement_zone": "block_edge",
                "decorative_only": True,
            })
    return objects
