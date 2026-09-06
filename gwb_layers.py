"""Shared GWB floor, bridge and manhole-network geometry (no rendering state)."""
from __future__ import annotations

LEVEL_LAYERS = {0: "ground", 1: "roof", 2: "first_floor", 3: "second_floor", -1: "underground"}


def pipe_network(features: list[dict], cell: int = 128) -> dict:
    """Connect every manhole by a deterministic Manhattan minimum spanning tree.

    The network follows its access points rather than copying the road network.
    Shared segments form junctions; one continuous service tunnel crosses banks.
    """
    nodes = sorted({(int(float(row["x"]) // cell), int(float(row["y"]) // cell))
                    for row in features if row.get("kind") == "manhole"})
    occupied = set(nodes)
    edges = []
    if nodes:
        joined, pending = {nodes[0]}, set(nodes[1:])
        while pending:
            _, a, b = min((abs(a[0]-b[0])+abs(a[1]-b[1]), a, b) for a in joined for b in pending)
            # Alternate elbow direction deterministically for a varied service plan.
            bend = (b[0], a[1]) if (a[0] + b[1]) % 2 else (a[0], b[1])
            for start, end in ((a, bend), (bend, b)):
                edges.append([list(start), list(end)])
                occupied.update((x, start[1]) for x in range(min(start[0], end[0]), max(start[0], end[0])+1))
                occupied.update((end[0], y) for y in range(min(start[1], end[1]), max(start[1], end[1])+1))
            joined.add(b)
            pending.remove(b)
    return {"cell_px": cell, "manholes": [list(p) for p in nodes],
            "cells": [list(p) for p in sorted(occupied)], "segments": edges}


def bridge_geometry(streets: list[dict], width: float = 1050) -> dict:
    road = next(row for row in streets if row.get("road_class") == "bridge")
    y = float(road["y1"])
    return {"x0": 6553, "x1": 9830, "y": y, "width": width,
            "barriers": [[6553, y + side * (width / 2 + 65) - 14, 3277, 28] for side in (-1, 1)]}


def add_playable_layers(data: dict, features: list[dict], streets: list[dict]) -> None:
    cell, width, height = data["cell_px"], data["width"], data["height"]
    roof = data["layers"]["roof"]
    for layer in ("first_floor", "second_floor"):
        data["layers"][layer] = [[layer if tile.startswith("bld_") else "void" for tile in row] for row in roof]
    network = pipe_network(features, cell)
    cells = {tuple(p) for p in network["cells"]}
    underground = [["void" for _ in range(width)] for _ in range(height)]
    for gx, gy in cells:
        mask = sum(bit for dx, dy, bit in ((0,-1,1),(1,0,2),(0,1,4),(-1,0,8)) if (gx+dx,gy+dy) in cells)
        underground[gy][gx] = f"pipe_{mask}"
    data["layers"]["underground"] = underground
    data["pipe_network"] = network
    data["bridge"] = bridge_geometry(streets)
    data["collision_rects"] = [{"layer": "ground", "rect": rect} for rect in data["bridge"]["barriers"]]
    data["level_layers"] = {str(k): v for k, v in LEVEL_LAYERS.items()}
    data["generation_scope"] = list(data["layers"])
    by = data["bridge"]["y"]
    def art(asset, x, y, w, h):
        gx, gy = int(x//cell), int(y//cell)
        data["objects"].append({"asset": asset, "gx": gx, "gy": gy,
            "offset_x_px": round(x-gx*cell), "offset_y_px": round(y-gy*cell),
            "width_px": w, "height_px": h, "layer": "ground", "rotation": 0,
            "visual_facing": "south", "decorative_only": True})
    for i in range(9):
        for side in (-1,1):
            art("gwb_truss",6553+(i+0.5)*3277/9-190,by+side*590-170,380,340)
    for x in (6330,9650):
        art("gwb_tower",x,by-665,400,1330)

    def center(p):
        return [(p[0]+0.5)*cell, (p[1]+0.5)*cell]

    def safe_ground(point):
        candidates = [(abs(x-point[0])+abs(y-point[1]),x,y) for y in range(height) for x in range(width)
                      if not data["layers"]["ground"][y][x].startswith(("bld_", "road_", "water_", "void"))]
        _, x, y = min(candidates)
        return (x,y)

    def trigger(oid, asset, source, level, target, next_level, prompt, building_id=""):
        x, y = source
        data["objects"].append({"object_id": oid, "asset": asset, "gx": x, "gy": y,
            "offset_x_px": cell//2-24, "offset_y_px": cell//2-30, "width_px": 48, "height_px": 60,
            "layer": LEVEL_LAYERS[level], "rotation": 0, "visual_facing": "south",
            "interaction_kind": "layer_transition", "interaction_level": level,
            "interaction_radius_px": 92, "interaction_prompt": prompt,
            "interaction_active": True, "collision_radius_px": 0,
            "target_level": next_level, "target_pos": center(target), "building_id": building_id})

    for building in data["building_synthesis"]["buildings"]:
        points = [tuple(p) for p in building["footprint_cells"]]
        # Southernmost complete cell always lies within the exact roof mask.
        roof_point = max(points, key=lambda p: (p[1], -p[0]))
        ground_point = safe_ground((roof_point[0],roof_point[1]+1))
        bid = building["building_id"]
        # Separate ascending and descending triggers avoid ambiguous interactions.
        other = min(points, key=lambda p: (p[1],p[0]))
        for suffix, src, level, dst, next_level, prompt in (
            ("enter",ground_point,0,roof_point,2,"ENTER 1ST FLOOR"),
            ("exit",roof_point,2,ground_point,0,"EXIT TO STREET"),
            ("up2",other,2,other,3,"STAIRS TO 2ND FLOOR"),
            ("down1",other,3,other,2,"STAIRS TO 1ST FLOOR"),
            ("roof",roof_point,3,roof_point,1,"STAIRS TO ROOF"),
            ("down2",roof_point,1,roof_point,3,"STAIRS TO 2ND FLOOR")):
            trigger(f"{bid}_{suffix}","roof_access_door" if level == 1 else "elevator_transition",src,level,dst,next_level,prompt,bid)

    for i, raw in enumerate(network["manholes"]):
        p = tuple(raw)
        # Preserve authored outdoor location in a walkable road/sidewalk cell.
        g = p if not data["layers"]["ground"][p[1]][p[0]].startswith(("bld_","water_")) else safe_ground(p)
        trigger(f"manhole_{i}_down","overlay_man_hole",g,0,p,-1,"ENTER SERVICE PIPES")
        trigger(f"manhole_{i}_up","overlay_man_hole",p,-1,g,0,"CLIMB TO STREET")
