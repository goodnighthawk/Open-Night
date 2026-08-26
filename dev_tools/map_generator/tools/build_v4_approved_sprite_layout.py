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
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "working_cosmetics" / "approved_v4_layout"

WORLD_W = 16384
WORLD_H = 10240
RIVER_W = round(WORLD_W * 0.20)
RIVER_X0 = (WORLD_W - RIVER_W) // 2
RIVER_X1 = RIVER_X0 + RIVER_W
BRIDGE_Y = 3560


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
        street("fl_hudson_terrace", "Hudson Terrace", "west", "vertical", 6100, 500, 6100, 9700, "secondary"),
        street("fl_lemoine", "Lemoine Ave", "west", "vertical", 4700, 600, 4700, 9600, "primary"),
        street("fl_center", "Center Ave", "west", "vertical", 3300, 900, 3300, 9300, "secondary"),
        street("fl_park", "Park Ave", "west", "vertical", 1900, 1000, 1900, 9200, "secondary"),
        street("fl_fletcher", "Fletcher Ave", "west", "vertical", 900, 1400, 900, 9000, "secondary"),
        # Fort Lee cross streets
        street("fl_bridge_plaza_n", "Bridge Plaza North", "west", "horizontal", 700, 3000, RIVER_X0, 3000, "primary"),
        street("fl_main", "Main St", "west", "horizontal", 500, 4300, RIVER_X0, 4300, "primary"),
        street("fl_bruce_reynolds", "Bruce Reynolds Blvd", "west", "horizontal", 600, 5900, RIVER_X0, 5900, "primary"),
        street("fl_center_cross", "Center Ave Connector", "west", "horizontal", 1200, 7350, 6100, 7350, "residential"),
        # Manhattan north/south routes
        street("ny_riverside", "Riverside Dr", "east", "vertical", 10250, 500, 10250, 9800, "secondary"),
        street("ny_broadway", "Broadway", "east", "vertical", 11600, 400, 12050, 9900, "primary"),
        street("ny_fort_washington", "Fort Washington Ave", "east", "vertical", 13100, 500, 13100, 6300, "secondary"),
        street("ny_cabrini", "Cabrini Blvd", "east", "vertical", 14300, 700, 14300, 5700, "residential"),
        street("ny_amsterdam", "Amsterdam Ave", "east", "vertical", 14500, 5200, 14500, 9900, "secondary"),
        street("ny_claremont", "Claremont Ave", "east", "vertical", 10650, 6500, 10650, 9800, "residential"),
        # Washington Heights / Columbia cross streets
        street("ny_w181", "W 181st St", "east", "horizontal", RIVER_X1, 1800, 16000, 1800, "primary"),
        street("ny_w178", "W 178th St", "east", "horizontal", RIVER_X1, 3100, 16000, 3100, "primary"),
        street("ny_w168", "W 168th St", "east", "horizontal", RIVER_X1, 4700, 16000, 4700, "secondary"),
        street("ny_w120", "W 120th St", "east", "horizontal", RIVER_X1, 7500, 16000, 7500, "secondary"),
        street("ny_w116", "W 116th St", "east", "horizontal", RIVER_X1, 8800, 16000, 8800, "primary"),
        # GWB crossing
        street("gwb", "George Washington Bridge", "bridge", "horizontal", 5700, BRIDGE_Y, 10680, BRIDGE_Y, "bridge"),
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
            "w": 250,
            "h": 190,
            "zone_id": zone,
            "sprite_role": "empty_house",
            "variant": 1 + (i % 6),
            "occupied": "false",
            "spawn_floor": 1,
            "spawn_mode": "inside_first_floor",
            "collision": "building",
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
        ("columbia_field", "athletic_field", 14500, 8850, 1000, 620, 0, "columbia"),
        ("fl_bridge_plaza", "commercial_landmark", 5200, 3300, 700, 430, 0, "fort_lee_north"),
    ]
    for sid, role, x, y, w, h, rot, zone in fixed:
        rows.append({"slot_id": sid, "sprite_role": role, "x": x, "y": y, "w": w, "h": h, "rotation": rot, "zone_id": zone, "collision": "semantic"})

    # Dense building bands provide structure without hard-coding a unique art
    # asset for every parcel.  A resolver can map role+variant to approved sprites.
    bands = [
        ("fl_commercial", 850, 3500, 10, 480, 360, 430, "commercial_midrise", "fort_lee_north"),
        ("fl_apartment", 900, 7700, 9, 540, 390, 470, "apartment_midrise", "fort_lee_south"),
        ("wh_brownstone", 10550, 3750, 10, 515, 330, 420, "brownstone", "washington_heights"),
        ("wh_apartment", 10550, 5050, 10, 515, 390, 460, "apartment_dense", "washington_heights"),
        ("mh_apartment", 11000, 6200, 8, 600, 390, 450, "apartment_dense", "morningside"),
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


def build_contract() -> list[dict]:
    return [
        {"key": "world_width", "value": WORLD_W, "notes": "Existing large GWB-corridor world-space convention."},
        {"key": "world_height", "value": WORLD_H, "notes": "Large vertical exploration footprint."},
        {"key": "hudson_width", "value": RIVER_W, "notes": "Exactly 20% of world width."},
        {"key": "hudson_west_x", "value": RIVER_X0, "notes": "West river boundary."},
        {"key": "hudson_east_x", "value": RIVER_X1, "notes": "East river boundary."},
        {"key": "empty_house_count", "value": len(EMPTY_HOUSES), "notes": "Future player housing; blank interiors."},
        {"key": "primary_crossing", "value": "George Washington Bridge", "notes": "Upper-middle map crossing."},
        {"key": "layout_status", "value": "approved", "notes": "Based on user-approved concept composition."},
    ]


def build() -> None:
    streets = build_streets()
    zones = build_zones()
    houses = build_empty_houses()
    slots = build_sprite_slots()
    contract = build_contract()

    assert len(houses) == 32
    assert RIVER_W == round(WORLD_W * 0.20)
    assert all(not (RIVER_X0 < int(h["x"]) < RIVER_X1) for h in houses)

    write_csv("streets.csv", ("street_id", "name", "side", "orientation", "x1", "y1", "x2", "y2", "road_class"), streets)
    write_csv("district_zones.csv", ("zone_id", "name", "x", "y", "w", "h", "density", "sprite_mix"), zones)
    write_csv("empty_houses.csv", ("housing_id", "x", "y", "w", "h", "zone_id", "sprite_role", "variant", "occupied", "spawn_floor", "spawn_mode", "collision"), houses)
    write_csv("sprite_slots.csv", ("slot_id", "sprite_role", "x", "y", "w", "h", "rotation", "zone_id", "collision"), slots)
    write_csv("layout_contract.csv", ("key", "value", "notes"), contract)

    print(f"[v4-layout] world={WORLD_W}x{WORLD_H}; Hudson={RIVER_W}px ({RIVER_W/WORLD_W:.0%})")
    print(f"[v4-layout] {len(streets)} streets; {len(houses)} empty houses; {len(slots)} sprite slots")
    print(f"[v4-layout] wrote {OUT}")


if __name__ == "__main__":
    build()
