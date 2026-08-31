from __future__ import annotations

"""Build the approved v4.0 Fort Lee -> Hudson -> Manhattan sprite layout.

This is an authored layout contract, not a painted background.  It provides
stable world-space slots that later rendering/runtime passes can resolve to the
approved sprite catalog while keeping collision, minimap and housing data on the
same coordinate system.

World space follows the existing GWB corridor convention (roughly 16384 x 10240).
The Hudson occupies one fifth of the map width and the GWB is the primary crossing.
"""

import csv
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "working_cosmetics" / "approved_v4_layout"

WORLD_W = 16384
WORLD_H = 10240
RIVER_W = round(WORLD_W * 0.20)
RIVER_X0 = (WORLD_W - RIVER_W) // 2
RIVER_X1 = RIVER_X0 + RIVER_W
BRIDGE_Y = 3560
VEHICLE_WIDTH = 105
REGULAR_ROAD_WIDTH = VEHICLE_WIDTH * 4
GWB_ROAD_WIDTH = VEHICLE_WIDTH * 10
ROAD_WIDTHS = {
    "bridge": GWB_ROAD_WIDTH,
    "primary": REGULAR_ROAD_WIDTH,
    "secondary": REGULAR_ROAD_WIDTH,
    "residential": REGULAR_ROAD_WIDTH,
}
# The rendered corridor adds 75 world pixels outside the asphalt on each side:
# a narrow but continuous v0.8-style curb/sidewalk/frontage band.
SIDEWALK_CLEARANCE = 55
CURB_AND_FRONTAGE = 20
COLUMBIA_FIELD = (14913, 9183, 1000, 620)


def write_csv(name: str, fields: tuple[str, ...], rows: list[dict]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / name).open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def street(street_id: str, name: str, side: str, orientation: str, x1: int, y1: int, x2: int, y2: int,
           road_class: str = "residential") -> dict:
    return {
        "street_id": street_id,
        "name": name,
        "side": side,
        "orientation": orientation,
        "x1": x1,
        "y1": y1,
        "x2": x2,
        "y2": y2,
        "road_class": road_class,
    }


def build_streets() -> list[dict]:
    # Game-friendly interpretation of real names around Fort Lee, the GWB,
    # Washington Heights and Columbia. Geometry is intentionally authored rather
    # than a literal GIS copy.
    rows = [
        # Fort Lee north/south routes
        street("fl_hudson_terrace", "Hudson Terrace", "west", "vertical", 6100, 0, 6100, WORLD_H, "secondary"),
        street("fl_lemoine", "Lemoine Ave", "west", "vertical", 4700, 0, 4700, WORLD_H, "primary"),
        street("fl_center", "Center Ave", "west", "vertical", 3300, 0, 3300, WORLD_H, "secondary"),
        street("fl_park", "Park Ave", "west", "vertical", 1900, 0, 1900, WORLD_H, "secondary"),
        street("fl_fletcher", "Fletcher Ave", "west", "vertical", 900, 0, 900, WORLD_H, "secondary"),
        # Fort Lee cross streets
        street("fl_bridge_plaza_n", "Bridge Plaza North", "west", "horizontal", 0, 3000, 6100, 3000, "primary"),
        street("fl_main", "Main St", "west", "horizontal", 0, 4300, 6100, 4300, "primary"),
        street("fl_bruce_reynolds", "Bruce Reynolds Blvd", "west", "horizontal", 0, 5900, 6100, 5900, "primary"),
        street("fl_center_cross", "Center Ave Connector", "west", "horizontal", 0, 7350, 6100, 7350, "residential"),
        # Manhattan north/south routes
        street("ny_riverside", "Riverside Dr", "east", "vertical", 10250, 0, 10250, WORLD_H, "secondary"),
        street("ny_broadway", "Broadway", "east", "vertical", 11600, 0, 12050, WORLD_H, "primary"),
        street("ny_fort_washington", "Fort Washington Ave", "east", "vertical", 13100, 0, 13100, WORLD_H, "secondary"),
        street("ny_cabrini", "Cabrini Blvd", "east", "vertical", 14300, 0, 14300, WORLD_H, "residential"),
        street("ny_amsterdam", "Amsterdam Ave", "east", "vertical", 14500, 0, 14500, WORLD_H, "secondary"),
        street("ny_claremont", "Claremont Ave", "east", "vertical", 10650, 0, 10650, WORLD_H, "residential"),
        # Washington Heights / Columbia cross streets
        street("ny_w181", "W 181st St", "east", "horizontal", 10250, 1800, WORLD_W, 1800, "primary"),
        street("ny_w178", "W 178th St", "east", "horizontal", 10250, 3100, WORLD_W, 3100, "primary"),
        street("ny_w168", "W 168th St", "east", "horizontal", 10250, 4700, WORLD_W, 4700, "secondary"),
        street("ny_w120", "W 120th St", "east", "horizontal", 10250, 7500, WORLD_W, 7500, "secondary"),
        street("ny_w116", "W 116th St", "east", "horizontal", 10250, 8800, WORLD_W, 8800, "primary"),
        # GWB crossing
        street("gwb", "George Washington Bridge", "bridge", "horizontal", 6100, BRIDGE_Y, 10250, BRIDGE_Y, "bridge"),
    ]
    return rows


def build_zones() -> list[dict]:
    return [
        {"zone_id": "fort_lee_north", "name": "Fort Lee North", "x": 250, "y": 300, "w": 6250, "h": 3900, "density": "medium", "sprite_mix": "houses,apartments,commercial,trees"},
        {"zone_id": "fort_lee_south", "name": "Fort Lee South", "x": 250, "y": 4450, "w": 6250, "h": 5450, "density": "medium", "sprite_mix": "houses,apartments,parks,trees"},
        {"zone_id": "hudson", "name": "Hudson River", "x": RIVER_X0, "y": 0, "w": RIVER_W, "h": WORLD_H, "density": "water", "sprite_mix": "water,piers,boats"},
        {"zone_id": "washington_heights", "name": "Washington Heights", "x": RIVER_X1, "y": 250, "w": WORLD_W - RIVER_X1 - 250, "h": 5700, "density": "high", "sprite_mix": "apartments,brownstones,commercial,trees"},
        {"zone_id": "morningside", "name": "Morningside Heights", "x": RIVER_X1, "y": 5950, "w": WORLD_W - RIVER_X1 - 250, "h": 4040, "density": "high", "sprite_mix": "apartments,brownstones,university,parks"},
        {"zone_id": "columbia", "name": "Columbia University", "x": 11100, "y": 7200, "w": 4550, "h": 2450, "density": "campus", "sprite_mix": "university,quad,trees,athletics"},
    ]


# Exactly 32 future player-housing slots.  They are deliberately distributed
# across both banks rather than collected in a single subdivision.
EMPTY_HOUSES = [
    # Fort Lee: 18
    ("house_01", 1150, 1050, "fort_lee_north"), ("house_02", 2150, 1050, "fort_lee_north"),
    ("house_03", 3600, 1100, "fort_lee_north"), ("house_04", 5150, 1100, "fort_lee_north"),
    ("house_05", 1250, 2200, "fort_lee_north"), ("house_06", 2650, 2200, "fort_lee_north"),
    ("house_07", 4050, 2250, "fort_lee_north"), ("house_08", 5450, 2250, "fort_lee_north"),
    ("house_09", 1050, 5050, "fort_lee_south"), ("house_10", 2350, 5050, "fort_lee_south"),
    ("house_11", 3750, 5100, "fort_lee_south"), ("house_12", 5350, 5100, "fort_lee_south"),
    ("house_13", 1200, 6550, "fort_lee_south"), ("house_14", 2650, 6550, "fort_lee_south"),
    ("house_15", 4100, 6650, "fort_lee_south"), ("house_16", 5500, 6650, "fort_lee_south"),
    ("house_17", 2300, 8150, "fort_lee_south"), ("house_18", 4750, 8250, "fort_lee_south"),
    # Manhattan: 14
    ("house_19", 10650, 950, "washington_heights"), ("house_20", 12400, 950, "washington_heights"),
    ("house_21", 13800, 1050, "washington_heights"), ("house_22", 15200, 1050, "washington_heights"),
    ("house_23", 10850, 2400, "washington_heights"), ("house_24", 12500, 2450, "washington_heights"),
    ("house_25", 13900, 2450, "washington_heights"), ("house_26", 15300, 2450, "washington_heights"),
    ("house_27", 10950, 5350, "washington_heights"), ("house_28", 12700, 5450, "washington_heights"),
    ("house_29", 15300, 5450, "washington_heights"),
    ("house_30", 11050, 6750, "morningside"), ("house_31", 12900, 6700, "morningside"),
    ("house_32", 15500, 6650, "morningside"),
]


def build_empty_houses() -> list[dict]:
    rows = []
    for i, (hid, x, y, zone) in enumerate(EMPTY_HOUSES):
        rows.append({
            "housing_id": hid,
            "x": x,
            "y": y,
            # Player houses use most of their parcel while retaining a narrow,
            # readable sidewalk frontage around the building.
            "w": 740,
            "h": 720,
            "zone_id": zone,
            "sprite_role": "empty_house",
            "variant": 1 + (i % 6),
            "occupied": "false",
            "spawn_floor": 1,
            "spawn_mode": "inside_first_floor",
            "collision": "building",
            "buzzer_enabled": "true",
            "buzzer_x": x + 370,
            "buzzer_y": y + 744,
            "buzzer_side": "south",
            "buzzer_interaction_radius": 54,
            "buzzer_collision_radius": 0,
        })
    return rows


def build_sprite_slots() -> list[dict]:
    rows: list[dict] = []

    # Bridge landmarks / waterfront anchors.
    fixed = [
        ("gwb_west_tower", "bridge_tower", 6400, BRIDGE_Y - 180, 220, 520, 0, "bridge"),
        ("gwb_east_tower", "bridge_tower", 9760, BRIDGE_Y - 180, 220, 520, 0, "bridge"),
        ("columbia_main", "university_landmark", 12800, 7900, 620, 520, 0, "columbia"),
        ("columbia_dome", "university_dome", 13700, 7900, 440, 440, 0, "columbia"),
        ("columbia_field", "athletic_field", 14913, 9183, 1000, 620, 0, "columbia"),
        ("fl_bridge_plaza", "commercial_landmark", 5200, 3300, 700, 430, 0, "fort_lee_north"),
    ]
    for sid, role, x, y, w, h, rot, zone in fixed:
        rows.append({"slot_id": sid, "sprite_role": role, "x": x, "y": y, "w": w, "h": h, "rotation": rot, "zone_id": zone, "collision": "semantic"})

    # Dense building bands provide structure without hard-coding a unique art
    # asset for every parcel.  A resolver can map role+variant to approved sprites.
    bands = [
        ("fl_commercial", 850, 3500, 10, 500, 460, 560, "commercial_midrise", "fort_lee_north"),
        ("fl_apartment", 900, 7700, 9, 570, 520, 590, "apartment_midrise", "fort_lee_south"),
        ("wh_brownstone", 10550, 3750, 10, 530, 480, 540, "brownstone", "washington_heights"),
        ("wh_apartment", 10550, 5050, 10, 530, 490, 580, "apartment_dense", "washington_heights"),
        ("mh_apartment", 11000, 6200, 8, 620, 570, 570, "apartment_dense", "morningside"),
    ]
    serial = 0
    for prefix, sx, sy, count, step, w, h, role, zone in bands:
        for j in range(count):
            x = sx + j * step
            # Small deterministic stagger avoids a sterile exact lattice.
            y = sy + (70 if j % 2 else 0)
            if RIVER_X0 - 120 < x < RIVER_X1 + 120:
                continue
            serial += 1
            rows.append({
                "slot_id": f"{prefix}_{j+1:02d}", "sprite_role": role,
                "x": x, "y": y, "w": w, "h": h, "rotation": 0,
                "zone_id": zone, "collision": "semantic",
            })

    # Waterfront props: sparse enough to preserve the visual width of the Hudson.
    for side, x, rot in (("west", RIVER_X0 - 180, 0), ("east", RIVER_X1 + 80, 180)):
        for j, y in enumerate(range(900, 9500, 1050), start=1):
            rows.append({
                "slot_id": f"{side}_pier_{j:02d}", "sprite_role": "small_pier",
                "x": x, "y": y, "w": 260, "h": 100, "rotation": rot,
                "zone_id": "hudson", "collision": "waterfront",
            })

    return rows


def _street_point(row: dict, fraction: float, offset: float = 0.0) -> tuple[int, int, int]:
    x1, y1, x2, y2 = (float(row[key]) for key in ("x1", "y1", "x2", "y2"))
    dx, dy = x2 - x1, y2 - y1
    length = max(1.0, math.hypot(dx, dy))
    nx, ny = -dy / length, dx / length
    x = x1 + dx * fraction + nx * offset
    y = y1 + dy * fraction + ny * offset
    # Vehicle sprite sheets point north, so add 90 degrees to the road vector.
    rotation = int(round(math.degrees(math.atan2(dy, dx)) + 90)) % 360
    return round(x), round(y), rotation


def build_transport(streets: list[dict]) -> list[dict]:
    roads = [row for row in streets if row["road_class"] != "residential"]
    rows = []
    for index in range(28):
        road = roads[index % len(roads)]
        fraction = 0.12 + ((index * 0.173) % 0.76)
        x, y, rotation = _street_point(road, fraction, -62 if index % 2 else 62)
        rows.append({
            "transport_id": f"traffic_{index + 1:02d}", "kind": "moving_vehicle",
            "x": x, "y": y, "rotation": rotation, "variant": index % 28,
            "route_id": road["street_id"], "occupied": "true",
        })
    parking_roads = [row for row in streets if row["orientation"] == "horizontal" and row["road_class"] != "bridge"]
    for index in range(18):
        road = parking_roads[index % len(parking_roads)]
        x, y, rotation = _street_point(road, 0.12 + ((index * 0.197) % 0.76), -145 if index % 2 else 145)
        rows.append({
            "transport_id": f"parking_{index + 1:02d}", "kind": "parked_vehicle" if index % 3 else "parking_space",
            "x": x, "y": y, "rotation": rotation, "variant": (index * 3) % 28,
            "route_id": road["street_id"], "occupied": str(index % 3 != 0).lower(),
        })
    return rows


def build_population(streets: list[dict], slots: list[dict]) -> list[dict]:
    walkable = [row for row in streets if row["road_class"] != "bridge"]
    rows = []
    for index in range(108):
        road = walkable[index % len(walkable)]
        fraction = 0.06 + ((index * 0.091) % 0.88)
        x, y, _rotation = _street_point(road, fraction, -260 if index % 2 else 260)
        rows.append({
            "entity_id": f"pedestrian_{index + 1:03d}", "kind": "pedestrian",
            "x": x, "y": y, "level": 0, "role": "ambient",
        })
    # Exactly three reciprocal dog/walker pairs from the v2.8/v3 baseline.
    for index in range(3):
        walker = rows[index * 17]
        walker["kind"] = "dog_walker"
        walker["role"] = f"walker_pair_{index + 1}"
        rows.append({
            "entity_id": f"dog_{index + 1:02d}", "kind": "dog",
            "x": int(walker["x"]) + 55, "y": int(walker["y"]) - 35,
            "level": 0, "role": f"walker_pair_{index + 1}",
        })
    building_slots = [row for row in slots if row["sprite_role"] not in {"small_pier", "bridge_tower", "athletic_field"}]
    for index, slot in enumerate(building_slots[:20]):
        rows.append({
            "entity_id": f"job_{index + 1:02d}",
            "kind": "supplier" if index % 2 == 0 else "buyer",
            "x": int(slot["x"]) + int(slot["w"]) // 2,
            "y": int(slot["y"]) + int(slot["h"]) // 2,
            "level": 1, "role": "rooftop_job",
        })
    return rows


def build_street_features(streets: list[dict]) -> list[dict]:
    rows = []
    serial = 0

    def add(kind: str, x: int, y: int, rotation: int = 0, group: str = "", **extra: object) -> None:
        nonlocal serial
        serial += 1
        asset_ids = {
            "street_tree": "v4_art_tree",
            "fire_hydrant": "v4_art_hydrant",
            "telephone": "v4_art_phone_box",
            "traffic_cone": "v4_art_cone",
            "crosswalk": "mark_zebra_crossing",
            "traffic_signal": "traffic_signal_dynamic",
        }
        rows.append({
            "feature_id": f"feature_{serial:03d}",
            "kind": kind,
            "x": x,
            "y": y,
            "rotation": rotation,
            "group": group,
            "asset_id": asset_ids.get(kind, ""),
            "controller": group if kind == "traffic_signal" else "",
            "cycle_states": "red_not_clear|yellow_not_clear|green_not_clear|red_clear|yellow_clear|green_clear" if kind == "traffic_signal" else "",
            **extra,
        })

    land_roads = [row for row in streets if row["road_class"] != "bridge"]
    for road_index, road in enumerate(land_roads):
        for step, fraction in enumerate((0.16, 0.38, 0.62, 0.84)):
            x, y, rotation = _street_point(road, fraction, -285 if (road_index + step) % 2 else 285)
            add("street_lamp", x, y, rotation, road["street_id"])
        for fraction in (0.27, 0.73):
            x, y, rotation = _street_point(road, fraction, 330)
            add("street_tree", x, y, rotation, road["street_id"])
        if road_index % 3 == 0:
            x, y, rotation = _street_point(road, 0.52, -330)
            add("fire_hydrant", x, y, rotation, road["street_id"])
        if road_index % 4 == 0:
            x, y, rotation = _street_point(road, 0.68, 350)
            add("telephone", x, y, rotation, road["street_id"])

    horizontal = [row for row in land_roads if row["orientation"] == "horizontal"]
    vertical = [row for row in land_roads if row["orientation"] == "vertical"]
    for hroad in horizontal:
        for vroad in vertical:
            y = float(hroad["y1"])
            vy1, vy2 = float(vroad["y1"]), float(vroad["y2"])
            if not min(vy1, vy2) <= y <= max(vy1, vy2):
                continue
            fraction = (y - vy1) / max(1.0, vy2 - vy1)
            x = float(vroad["x1"]) + (float(vroad["x2"]) - float(vroad["x1"])) * fraction
            if not min(float(hroad["x1"]), float(hroad["x2"])) <= x <= max(float(hroad["x1"]), float(hroad["x2"])):
                continue

            ix, iy = round(x), round(y)
            hhalf = ROAD_WIDTHS[hroad["road_class"]] * 0.5
            vhalf = ROAD_WIDTHS[vroad["road_class"]] * 0.5
            hclear, vclear = round(hhalf + 105), round(vhalf + 105)
            group = f"{hroad['street_id']}+{vroad['street_id']}"

            min_hx, max_hx = sorted((float(hroad["x1"]), float(hroad["x2"])))
            min_vy, max_vy = sorted((float(vroad["y1"]), float(vroad["y2"])))
            arms = {
                "north": iy > min_vy + 1,
                "south": iy < max_vy - 1,
                "west": ix > min_hx + 1,
                "east": ix < max_hx - 1,
            }
            crossing_specs = {
                "north": (ix, iy - hclear, 0, ROAD_WIDTHS[vroad["road_class"]] + 130),
                "south": (ix, iy + hclear, 0, ROAD_WIDTHS[vroad["road_class"]] + 130),
                "west": (ix - vclear, iy, 90, ROAD_WIDTHS[hroad["road_class"]] + 130),
                "east": (ix + vclear, iy, 90, ROAD_WIDTHS[hroad["road_class"]] + 130),
            }
            # Two direction-specific signal assemblies share each block corner.
            # Mount their bases along the perpendicular sidewalk legs instead
            # of nearly on top of one another at a 34x34 diagonal offset.
            hsignal = round(hhalf + 35)
            vsignal = round(vhalf + 35)
            signal_specs = {
                "north": ((ix - vsignal, iy - hclear, 0), (ix + vsignal, iy - hclear, 0)),
                "south": ((ix - vsignal, iy + hclear, 180), (ix + vsignal, iy + hclear, 180)),
                "west": ((ix - vclear, iy - hsignal, 270), (ix - vclear, iy + hsignal, 270)),
                "east": ((ix + vclear, iy - hsignal, 90), (ix + vclear, iy + hsignal, 90)),
            }
            crossing_arms = dict(arms)
            if vroad["street_id"] == "fl_hudson_terrace" and not arms["east"]:
                crossing_arms = {name: name == "west" and exists for name, exists in arms.items()}
            elif vroad["street_id"] == "ny_riverside" and not arms["west"]:
                crossing_arms = {name: name == "east" and exists for name, exists in arms.items()}
            for approach, exists in arms.items():
                if not exists:
                    continue
                for sx, sy, signal_rotation in signal_specs[approach]:
                    add("traffic_signal", sx, sy, signal_rotation, group)
            for approach, exists in crossing_arms.items():
                if not exists:
                    continue
                cx, cy, rotation, crossing_length = crossing_specs[approach]
                add("crosswalk", cx, cy, rotation, f"{group}:{approach}", length=crossing_length)

    # One recognizable five-cone road closure and several manhole transitions.
    for index in range(5):
        add("traffic_cone", 2750 + index * 125, 5900, 0, "bruce_reynolds_closure")
    primary = [row for row in streets if row["road_class"] in {"primary", "secondary"}]
    for index, road in enumerate(primary[:10]):
        x, y, rotation = _street_point(road, 0.34 + (index % 3) * 0.13)
        add("manhole", x, y, rotation, road["street_id"])
    return rows


def build_access(houses: list[dict], slots: list[dict]) -> list[dict]:
    rows = []
    for house in houses:
        rows.append({
            "access_id": f"door_{house['housing_id']}", "building_id": house["housing_id"],
            "kind": "player_house_door", "x": house["buzzer_x"], "y": int(house["y"]) + int(house["h"]),
            "level": 0, "public": "false", "buzzer_enabled": "true",
            "asset_id": "entrance_door", "interaction": "enter_interior",
            "interaction_radius": 72, "collision_radius": 0,
            "destination": f"interior:{house['housing_id']}", "available_floors": "",
        })
    public_slots = [row for row in slots if row["sprite_role"] not in {"small_pier", "bridge_tower", "athletic_field"}]
    for index, slot in enumerate(public_slots[:30]):
        rows.append({
            "access_id": f"public_door_{index + 1:02d}", "building_id": slot["slot_id"],
            "kind": "public_door", "x": int(slot["x"]) + int(slot["w"]) // 2,
            "y": int(slot["y"]) + int(slot["h"]), "level": 0,
            "public": "true", "buzzer_enabled": "false",
            "asset_id": "entrance_door", "interaction": "enter_interior",
            "interaction_radius": 72, "collision_radius": 0,
            "destination": f"interior:{slot['slot_id']}", "available_floors": "",
        })
        if index % 2 == 0:
            rows.append({
                "access_id": f"fire_escape_{index + 1:02d}", "building_id": slot["slot_id"],
                "kind": "fire_escape", "x": int(slot["x"]) + int(slot["w"]),
                "y": int(slot["y"]) + int(slot["h"]) // 2, "level": 0,
                "public": "true", "buzzer_enabled": "false",
                "asset_id": "fire_escape_ladder", "interaction": "travel_connected_level",
                "interaction_radius": 66, "collision_radius": 0,
                "destination": "roof:1", "available_floors": "0|1",
            })
    if public_slots:
        demo = public_slots[0]
        center_x = int(demo["x"]) + int(demo["w"]) // 2
        center_y = int(demo["y"]) + int(demo["h"]) // 2
        rows.extend((
            {
                "access_id": "approved_demo_roof_access", "building_id": demo["slot_id"],
                "kind": "roof_access_door", "x": center_x - 80, "y": center_y,
                "level": 1, "public": "true", "buzzer_enabled": "false",
                "asset_id": "roof_access_door", "interaction": "travel_to_upper_interior",
                "interaction_radius": 72, "collision_radius": 0,
                "destination": f"upper_interior:{demo['slot_id']}", "available_floors": "1|roof",
            },
            {
                "access_id": "approved_demo_elevator", "building_id": demo["slot_id"],
                "kind": "elevator_transition", "x": center_x + 80,
                "y": int(demo["y"]) + int(demo["h"]) - 45,
                "level": 0, "public": "true", "buzzer_enabled": "false",
                "asset_id": "elevator_transition", "interaction": "select_floor",
                "interaction_radius": 78, "collision_radius": 0,
                "destination": "", "available_floors": "0|1|roof",
            },
        ))
    return rows


def _road_radius(road: dict) -> float:
    return ROAD_WIDTHS.get(str(road.get("road_class", "residential")), 235) * 0.5 + SIDEWALK_CLEARANCE + CURB_AND_FRONTAGE


def _legal_intervals(start: int, end: int, roads: list[dict], axis: str) -> list[tuple[int, int]]:
    """Return parcel spans outside full road+curb+sidewalk+frontage corridors."""
    cursor = float(start) + 90.0
    spans: list[tuple[int, int]] = []
    key = "x1" if axis == "x" else "y1"
    for road in sorted(roads, key=lambda row: float(row[key])):
        center = float(road[key])
        radius = _road_radius(road)
        left, right = center - radius, center + radius
        if left - cursor >= 360:
            spans.append((round(cursor), round(left)))
        cursor = max(cursor, right)
    if float(end) - 90.0 - cursor >= 360:
        spans.append((round(cursor), round(float(end) - 90.0)))
    return spans


def _split_long_span(span: tuple[int, int], serial: int) -> list[tuple[int, int]]:
    start, end = span
    length = end - start
    # Large v3 parcels are divided by narrow service alleys until their street
    # wall is substantial but no longer a single repetitive mega-rectangle.
    if length < 900:
        return [span]
    alley = 70
    midpoint = (start + end) // 2 + ((serial % 3) - 1) * 45
    left = (start, midpoint - alley // 2)
    right = (midpoint + alley // 2, end)
    return _split_long_span(left, serial + 1) + _split_long_span(right, serial + 2)


def _building_overlaps_road(building: dict, road: dict) -> bool:
    bx0, by0 = float(building["x"]), float(building["y"])
    bx1, by1 = bx0 + float(building["w"]), by0 + float(building["h"])
    x1, y1, x2, y2 = (float(road[key]) for key in ("x1", "y1", "x2", "y2"))
    radius = _road_radius(road)
    # Intersect the road centerline with the building rectangle expanded by the
    # complete asphalt + curb + sidewalk + frontage radius. This handles the
    # gently diagonal Broadway route as well as axis-aligned streets.
    left, right = bx0 - radius, bx1 + radius
    top, bottom = by0 - radius, by1 + radius
    dx, dy = x2 - x1, y2 - y1
    t0, t1 = 0.0, 1.0
    for p, q in ((-dx, x1 - left), (dx, right - x1), (-dy, y1 - top), (dy, bottom - y1)):
        if abs(p) < 1e-9:
            if q < 0:
                return False
            continue
        ratio = q / p
        if p < 0:
            t0 = max(t0, ratio)
        else:
            t1 = min(t1, ratio)
        if t0 > t1:
            return False
    return True


def _overlaps_reserved_field(building: dict) -> bool:
    fx, fy, fw, fh = COLUMBIA_FIELD
    bx, by = float(building["x"]), float(building["y"])
    bw, bh = float(building["w"]), float(building["h"])
    return bx < fx + fw and bx + bw > fx and by < fy + fh and by + bh > fy


def build_legal_buildings(streets: list[dict]) -> list[dict]:
    """Apply the v0.8/v3 road-bounded parcel and narrow-sidewalk grammar."""
    by_id = {row["street_id"]: row for row in streets}
    specs = (
        (
            "fort_lee", (250, 300, RIVER_X0 - 55, 9940),
            ("fl_fletcher", "fl_park", "fl_center", "fl_lemoine", "fl_hudson_terrace"),
            ("fl_bridge_plaza_n", "fl_main", "fl_bruce_reynolds", "fl_center_cross"),
        ),
        (
            "washington_heights", (RIVER_X1 + 55, 250, 16130, 5900),
            ("ny_riverside", "ny_claremont", "ny_broadway", "ny_fort_washington", "ny_cabrini", "ny_amsterdam"),
            ("ny_w181", "ny_w178", "ny_w168"),
        ),
        (
            "morningside", (RIVER_X1 + 55, 5950, 16130, 9990),
            ("ny_riverside", "ny_claremont", "ny_broadway", "ny_fort_washington", "ny_cabrini", "ny_amsterdam"),
            ("ny_w120", "ny_w116"),
        ),
    )
    buildings: list[dict] = []
    serial = 0
    shapes = ("rectangle", "notch_ne", "rectangle", "notch_sw", "courtyard", "notch_nw", "rectangle", "notch_se")
    for district, bounds, vertical_ids, horizontal_ids in specs:
        bx0, by0, bx1, by1 = bounds
        xs = _legal_intervals(bx0, bx1, [by_id[name] for name in vertical_ids], "x")
        ys = _legal_intervals(by0, by1, [by_id[name] for name in horizontal_ids], "y")
        for raw_x in xs:
            for raw_y in ys:
                xspans = _split_long_span(raw_x, serial)
                yspans = _split_long_span(raw_y, serial + 1)
                for xa, xb in xspans:
                    for ya, yb in yspans:
                        serial += 1
                        # v0.8 dense-block law: setbacks vary modestly but never
                        # surrender most of a legal parcel back to empty paving.
                        desired_setback = 20 + (serial % 3) * 15
                        max_legal_setback = max(15, min((xb - xa - 340) // 2, (yb - ya - 340) // 2))
                        setback = min(desired_setback, max_legal_setback)
                        x, y = xa + setback, ya + setback
                        w, h = xb - xa - setback * 2, yb - ya - setback * 2
                        if w < 340 or h < 340:
                            continue
                        shape = shapes[serial % len(shapes)]
                        if shape == "courtyard" and (w < 850 or h < 850):
                            shape = "notch_ne"
                        if shape.startswith("notch") and (w < 560 or h < 560):
                            shape = "rectangle"
                        zone = district
                        if district == "fort_lee":
                            zone = "fort_lee_north" if y + h / 2 < 4300 else "fort_lee_south"
                        if district == "morningside" and x + w / 2 > 11900 and y + h / 2 > 7200:
                            zone = "columbia"
                        envelope = max(1, (xb - xa) * (yb - ya))
                        buildings.append({
                            "building_id": f"legal_building_{len(buildings) + 1:03d}",
                            "x": x, "y": y, "w": w, "h": h,
                            "shape": shape, "zone_id": zone,
                            "lot_id": f"{district}_lot_{serial:03d}",
                            "lot_x": xa, "lot_y": ya, "lot_w": xb - xa, "lot_h": yb - ya,
                            "parcel_occupancy": round((w * h) / envelope, 3),
                            "ground_roof_registration": "exact",
                        })
    buildings = [row for row in buildings if not any(_building_overlaps_road(row, road) for road in streets)]
    for index, row in enumerate(buildings, 1):
        row["building_id"] = f"legal_building_{index:03d}"
    courtyard_candidates = sorted(
        (row for row in buildings if min(int(row["w"]), int(row["h"])) >= 700),
        key=lambda row: int(row["w"]) * int(row["h"]),
        reverse=True,
    )
    for row in courtyard_candidates[:2]:
        row["shape"] = "courtyard"
    return buildings


def build_pavement_blocks(streets: list[dict]) -> list[dict]:
    """Continuous road-bounded block surfaces, independent of building lots."""
    by_id = {row["street_id"]: row for row in streets}
    specs = (
        ("fort_lee", (250, 300, RIVER_X0 - 55, 9940),
         ("fl_fletcher", "fl_park", "fl_center", "fl_lemoine", "fl_hudson_terrace"),
         ("fl_bridge_plaza_n", "fl_main", "fl_bruce_reynolds", "fl_center_cross")),
        ("washington_heights", (RIVER_X1 + 55, 250, 16130, 5900),
         ("ny_riverside", "ny_claremont", "ny_broadway", "ny_fort_washington", "ny_cabrini", "ny_amsterdam"),
         ("ny_w181", "ny_w178", "ny_w168")),
        ("morningside", (RIVER_X1 + 55, 5950, 16130, 9990),
         ("ny_riverside", "ny_claremont", "ny_broadway", "ny_fort_washington", "ny_cabrini", "ny_amsterdam"),
         ("ny_w120", "ny_w116")),
    )
    rows: list[dict] = []
    for district, bounds, vertical_ids, horizontal_ids in specs:
        bx0, by0, bx1, by1 = bounds
        xs = _legal_intervals(bx0, bx1, [by_id[name] for name in vertical_ids], "x")
        ys = _legal_intervals(by0, by1, [by_id[name] for name in horizontal_ids], "y")
        for xa, xb in xs:
            for ya, yb in ys:
                rows.append({
                    "block_id": f"pavement_block_{len(rows) + 1:03d}",
                    "district": district,
                    "x": xa, "y": ya, "w": xb - xa, "h": yb - ya,
                    "surface": "city_block_small_pavement",
                })
    return rows


def audit_legal_buildings(buildings: list[dict], streets: list[dict]) -> None:
    for building in buildings:
        bx0, by0 = float(building["x"]), float(building["y"])
        bx1, by1 = bx0 + float(building["w"]), by0 + float(building["h"])
        assert bx1 <= RIVER_X0 or bx0 >= RIVER_X1, building["building_id"]
        assert float(building["w"]) >= 340 and float(building["h"]) >= 340
        assert float(building["parcel_occupancy"]) >= 0.55
        assert building["ground_roof_registration"] == "exact"
        for road in streets:
            assert not _building_overlaps_road(building, road), (building["building_id"], road["street_id"])
    shapes = {row["shape"] for row in buildings}
    assert {"rectangle", "courtyard"} <= shapes
    assert any(str(shape).startswith("notch_") for shape in shapes)


def _even_selection(rows: list[dict], count: int) -> list[dict]:
    if count <= 0:
        return []
    return [rows[min(len(rows) - 1, (index * len(rows)) // count)] for index in range(count)]


def bind_legal_buildings(buildings: list[dict]) -> tuple[list[dict], list[dict]]:
    west = [row for row in buildings if row["zone_id"].startswith("fort_lee")]
    east = [row for row in buildings if not row["zone_id"].startswith("fort_lee")]
    selected_ids = {row["building_id"] for row in _even_selection(west, 18) + _even_selection(east, 14)}
    houses: list[dict] = []
    slots: list[dict] = []
    for building in buildings:
        common = {key: building[key] for key in ("x", "y", "w", "h", "shape", "zone_id", "lot_id", "lot_x", "lot_y", "lot_w", "lot_h", "parcel_occupancy", "ground_roof_registration")}
        if building["building_id"] in selected_ids:
            index = len(houses) + 1
            houses.append({
                "housing_id": f"house_{index:02d}", **common,
                "sprite_role": "player_house", "variant": 1 + (index - 1) % 6,
                "occupied": "false", "spawn_floor": 1, "spawn_mode": "inside_first_floor",
                "collision": "building", "buzzer_enabled": "true",
                "buzzer_x": int(common["x"]) + int(common["w"]) // 2,
                "buzzer_y": int(common["y"]) + int(common["h"]) + 24,
                "buzzer_side": "south",
                "buzzer_interaction_radius": 54,
                "buzzer_collision_radius": 0,
            })
        else:
            zone = str(common["zone_id"])
            role = "brownstone" if zone == "washington_heights" else "university_landmark" if zone == "columbia" else "apartment_dense" if zone == "morningside" else "apartment_midrise"
            slots.append({
                "slot_id": building["building_id"], **common,
                "sprite_role": role, "rotation": 0, "collision": "semantic",
            })

    # Preserve the established 32 housing assignments and stable building IDs,
    # then clear only the two public/NPC masses beneath the field reservation.
    assert not any(_overlaps_reserved_field(house) for house in houses)
    slots = [slot for slot in slots if not _overlaps_reserved_field(slot)]

    # Infrastructure remains independent of building parcels.
    for sid, role, x, y, w, h, zone in (
        ("gwb_west_tower", "bridge_tower", 6400, BRIDGE_Y - 260, 260, 620, "bridge"),
        ("gwb_east_tower", "bridge_tower", 9720, BRIDGE_Y - 260, 260, 620, "bridge"),
        ("columbia_field", "athletic_field", *COLUMBIA_FIELD, "columbia"),
    ):
        slots.append({"slot_id": sid, "sprite_role": role, "x": x, "y": y, "w": w, "h": h, "shape": "rectangle", "rotation": 0, "zone_id": zone, "collision": "semantic", "lot_id": "landmark", "lot_x": x, "lot_y": y, "lot_w": w, "lot_h": h, "parcel_occupancy": 1.0, "ground_roof_registration": "exact"})
    for side, x, rotation in (("west", RIVER_X0 - 180, 0), ("east", RIVER_X1 + 80, 180)):
        for index, y in enumerate(range(900, 9500, 1050), 1):
            slots.append({"slot_id": f"{side}_pier_{index:02d}", "sprite_role": "small_pier", "x": x, "y": y, "w": 260, "h": 100, "shape": "rectangle", "rotation": rotation, "zone_id": "hudson", "collision": "waterfront", "lot_id": "waterfront", "lot_x": x, "lot_y": y, "lot_w": 260, "lot_h": 100, "parcel_occupancy": 1.0, "ground_roof_registration": "exact"})
    return houses, slots


def build_contract() -> list[dict]:
    return [
        {"key": "world_width", "value": WORLD_W, "notes": "Existing large GWB-corridor world-space convention."},
        {"key": "world_height", "value": WORLD_H, "notes": "Large vertical exploration footprint."},
        {"key": "hudson_width", "value": RIVER_W, "notes": "Exactly 20% of world width."},
        {"key": "hudson_west_x", "value": RIVER_X0, "notes": "West river boundary."},
        {"key": "hudson_east_x", "value": RIVER_X1, "notes": "East river boundary."},
        {"key": "city_block_world_scale", "value": 0.5, "notes": "Native 256px city_block modules render as 128 world units."},
        {"key": "vehicle_width", "value": VEHICLE_WIDTH, "notes": "Shared overview car-width unit."},
        {"key": "regular_road_width", "value": REGULAR_ROAD_WIDTH, "notes": "Four car widths across."},
        {"key": "gwb_road_width", "value": GWB_ROAD_WIDTH, "notes": "Ten car widths across."},
        {"key": "regular_lane_count", "value": 4, "notes": "Four marked lanes on ordinary roads."},
        {"key": "gwb_lane_count", "value": 9, "notes": "Nine marked lanes across the bridge deck."},
        {"key": "empty_house_count", "value": len(EMPTY_HOUSES), "notes": "Future player housing; blank interiors."},
        {"key": "primary_crossing", "value": "George Washington Bridge", "notes": "Upper-middle map crossing."},
        {"key": "layout_status", "value": "approved", "notes": "Based on user-approved concept composition."},
    ]


def build() -> None:
    streets = build_streets()
    zones = build_zones()
    legal_buildings = build_legal_buildings(streets)
    audit_legal_buildings(legal_buildings, streets)
    pavement_blocks = build_pavement_blocks(streets)
    houses, slots = bind_legal_buildings(legal_buildings)
    transport = build_transport(streets)
    population = build_population(streets, slots)
    street_features = build_street_features(streets)
    access = build_access(houses, slots)
    contract = build_contract()

    assert len(houses) == 32
    assert RIVER_W == round(WORLD_W * 0.20)
    assert all(not (RIVER_X0 < int(h["x"]) < RIVER_X1) for h in houses)
    assert sum(row["kind"] == "moving_vehicle" for row in transport) == 28
    assert sum(row["kind"] in {"pedestrian", "dog_walker"} for row in population) == 108
    assert sum(row["kind"] == "dog" for row in population) == 3
    assert sum(row["kind"] in {"supplier", "buyer"} for row in population) == 20
    assert all(row["buzzer_enabled"] == "true" for row in access if row["kind"] == "player_house_door")
    assert all(row["buzzer_enabled"] == "false" for row in access if row["kind"] != "player_house_door")

    write_csv("streets.csv", ("street_id", "name", "side", "orientation", "x1", "y1", "x2", "y2", "road_class"), streets)
    write_csv("district_zones.csv", ("zone_id", "name", "x", "y", "w", "h", "density", "sprite_mix"), zones)
    write_csv("empty_houses.csv", ("housing_id", "x", "y", "w", "h", "shape", "zone_id", "lot_id", "lot_x", "lot_y", "lot_w", "lot_h", "parcel_occupancy", "ground_roof_registration", "sprite_role", "variant", "occupied", "spawn_floor", "spawn_mode", "collision", "buzzer_enabled", "buzzer_x", "buzzer_y", "buzzer_side", "buzzer_interaction_radius", "buzzer_collision_radius"), houses)
    write_csv("sprite_slots.csv", ("slot_id", "sprite_role", "x", "y", "w", "h", "shape", "rotation", "zone_id", "collision", "lot_id", "lot_x", "lot_y", "lot_w", "lot_h", "parcel_occupancy", "ground_roof_registration"), slots)
    write_csv("transport.csv", ("transport_id", "kind", "x", "y", "rotation", "variant", "route_id", "occupied"), transport)
    write_csv("population.csv", ("entity_id", "kind", "x", "y", "level", "role"), population)
    write_csv("street_features.csv", ("feature_id", "kind", "x", "y", "rotation", "group", "length", "asset_id", "controller", "cycle_states"), street_features)
    write_csv("building_access.csv", ("access_id", "building_id", "kind", "x", "y", "level", "public", "buzzer_enabled", "asset_id", "interaction", "interaction_radius", "collision_radius", "destination", "available_floors"), access)
    write_csv("pavement_blocks.csv", ("block_id", "district", "x", "y", "w", "h", "surface"), pavement_blocks)
    write_csv("layout_contract.csv", ("key", "value", "notes"), contract)

    print(f"[v4-layout] world={WORLD_W}x{WORLD_H}; Hudson={RIVER_W}px ({RIVER_W/WORLD_W:.0%})")
    print(f"[v4-layout] {len(streets)} streets; {len(houses)} player houses; {len(slots)} sprite slots")
    print(f"[v4-layout] {len(transport)} vehicles/parking; {len(population)} population/jobs; {len(street_features)} street features")
    print(f"[v4-layout] wrote {OUT}")


if __name__ == "__main__":
    build()
