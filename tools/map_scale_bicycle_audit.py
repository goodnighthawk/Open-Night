from __future__ import annotations

import csv
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
MAP = ROOT / "mapfiles" / "data" / "map_001_gwb_corridor"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from common import point_in_water, point_near_road
from mapfiles.loader import load_map_folder


def rows(name: str) -> list[dict]:
    with (MAP / name).open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def fail(errors: list[str], message: str) -> None:
    errors.append(message)


def main() -> int:
    errors: list[str] = []
    roads = rows("roads.csv")
    for road in roads:
        try:
            ratio = float(road["width"]) / float(road["base_width"])
        except (KeyError, TypeError, ValueError, ZeroDivisionError):
            fail(errors, f"{road.get('road_id','road')}: missing valid base_width/width")
            continue
        if not (0.75 <= ratio <= 1.25):
            fail(errors, f"{road['road_id']}: authored/runtime asphalt ratio {ratio:.3f} is outside 0.75..1.25")

    sidewalk_sides: dict[str, set[str]] = {}
    for row in rows("sidewalks.csv"):
        sidewalk_sides.setdefault(str(row.get("road_id", "")), set()).add(str(row.get("side", "")))
    for road in roads:
        if str(road.get("highway", "")).lower() == "motorway":
            continue
        if sidewalk_sides.get(str(road["road_id"])) != {"left", "right"}:
            fail(errors, f"{road['road_id']}: ordinary road lacks two-sided sidewalk semantics")

    cfg = load_map_folder(MAP)
    tunnel_props = [p for p in cfg.get("street_props", []) if p.get("kind") == "edge_tunnel"]
    expected_tunnels = int(float(cfg.get("edge_tunnel_count", 0)))
    if len(tunnel_props) != expected_tunnels:
        fail(errors, f"edge tunnels: expected {expected_tunnels}, loaded {len(tunnel_props)}")

    bike_scale = float(cfg.get("bicycle_render_scale", 99.0))
    if not (0.25 <= bike_scale < 1.0):
        fail(errors, f"bicycle_render_scale={bike_scale:g}; compact bike must be below 1x")

    unsafe_routes: set[str] = set()
    for route in cfg.get("bicycle_routes", []) or []:
        points = route.get("waypoints", []) or []
        for a, b in zip(points, points[1:]):
            sample_count = max(1, int(math.hypot(float(b[0])-float(a[0]), float(b[1])-float(a[1])) // 10))
            for index in range(sample_count + 1):
                t = index / sample_count
                x = float(a[0]) + (float(b[0])-float(a[0])) * t
                y = float(a[1]) + (float(b[1])-float(a[1])) * t
                if point_in_water(x, y, cfg) and not point_near_road(x, y, cfg, bridge_only=True):
                    unsafe_routes.add(str(route.get("id", "route")))
                    break
            if str(route.get("id", "route")) in unsafe_routes:
                break
    if unsafe_routes:
        fail(errors, "exposed-water bicycle routes: " + ", ".join(sorted(unsafe_routes)))

    for index, spawn in enumerate(cfg.get("parked_bicycle_spawns", []) or []):
        x, y = float(spawn[0]), float(spawn[1])
        if point_in_water(x, y, cfg) and not point_near_road(x, y, cfg, bridge_only=True):
            fail(errors, f"parked bicycle {index} is on exposed water")

    server_source = (ROOT / "server.py").read_text(encoding="utf-8")
    required = (
        "def _bicycle_map_blocked(",
        "def _bicycle_hits_vehicle(",
        "def _vehicle_hits_bicycle(",
        "and not _vehicle_hits_bicycle(car,nx,ny,proposed_angle)",
    )
    for token in required:
        if token not in server_source:
            fail(errors, f"server collision contract missing: {token}")
    riding_block = server_source[server_source.find("if session.riding_bicycle_id:", server_source.find("async def game_loop")):]
    riding_block = riding_block[:riding_block.find("if session.driving_vehicle_id:")]
    if "for other in bicycles:" in riding_block:
        fail(errors, "player bicycles still hard-block one another")

    art_source = (ROOT / "bicycle_art.py").read_text(encoding="utf-8")
    if "strict-top-down" not in art_source.replace(" ", "-").lower() and "top-down bicycle" not in art_source.lower():
        fail(errors, "bicycle art no longer declares its top-down projection")

    if errors:
        print("MAP SCALE / BICYCLE AUDIT: FAIL")
        for error in errors:
            print(" -", error)
        return 1
    print(
        "MAP SCALE / BICYCLE AUDIT: PASS — "
        f"{len(roads)} roads at approved authored scale, {len(tunnel_props)} edge tunnels, "
        f"{len(cfg.get('bicycle_routes', []))} water-safe bicycle routes, bike scale {bike_scale:g}x."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
