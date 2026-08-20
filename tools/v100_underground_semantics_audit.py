#!/usr/bin/env python3
"""Validate v1.0 Underground traversal semantics before art/runtime promotion."""
from __future__ import annotations

import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from common import blocked, point_near_road, resolve_level_transition
from mapfiles.loader import load_map_folder

MAP_DIR = ROOT / "mapfiles" / "data" / "map_001_gwb_corridor"
UNDERGROUND_LEVEL = -1
REQUIRED_ROADS = {
    "ug_broadway_spine",
    "ug_181_crosspassage",
    "ug_gwb_service_branch",
}
REQUIRED_STAIRS = {
    "ug_broadway_181_stairs",
    "ug_amsterdam_181_stairs",
    "ug_riverside_gwb_stairs",
}


def fail(message: str):
    raise SystemExit(message)


def main():
    m = load_map_folder(MAP_DIR)
    levels = {int(row.get("id", 0)): row for row in m.get("levels", []) or []}
    if UNDERGROUND_LEVEL not in levels:
        fail("Underground level -1 is not registered")
    if not bool(levels[UNDERGROUND_LEVEL].get("walkable", True)):
        fail("Underground level -1 is not walkable")

    roads = {
        str(row.get("id", "")): row
        for row in m.get("roads", []) or []
        if int(row.get("level", 0) or 0) == UNDERGROUND_LEVEL
    }
    missing_roads = sorted(REQUIRED_ROADS - set(roads))
    if missing_roads:
        fail(f"Missing Underground roads: {missing_roads}")

    for rid in sorted(REQUIRED_ROADS):
        road = roads[rid]
        if not bool(road.get("walkable", True)):
            fail(f"Underground road {rid} is not walkable")
        pts = road.get("points", []) or []
        if len(pts) < 2:
            fail(f"Underground road {rid} has fewer than two points")
        # Sample every authored segment midpoint. These are the exact semantics
        # that art follows, so collision must accept them all at level -1.
        for a, b in zip(pts, pts[1:]):
            mx = (float(a[0]) + float(b[0])) * 0.5
            my = (float(a[1]) + float(b[1])) * 0.5
            if not point_near_road(mx, my, m, level=UNDERGROUND_LEVEL):
                fail(f"Underground road {rid} midpoint is not found by same-level lookup")
            if blocked(mx, my, m, level=UNDERGROUND_LEVEL):
                fail(f"Underground road {rid} midpoint is blocked: {(mx, my)}")

    # The three initial corridors deliberately intersect at authored shared
    # coordinates so the network is connected without relying on art overlap.
    shared = {
        "broadway_181": (12160.0, 4672.0),
        "broadway_gwb": (12288.0, 6144.0),
    }
    for label, (x, y) in shared.items():
        touching = [rid for rid, road in roads.items() if point_near_road(x, y, {**m, "roads": [road]}, level=UNDERGROUND_LEVEL)]
        if len(touching) < 2:
            fail(f"Underground network junction {label} is not shared by two corridors: {touching}")
        if blocked(x, y, m, level=UNDERGROUND_LEVEL):
            fail(f"Underground network junction {label} is blocked")

    connectors = {
        str(row.get("id", "")): row
        for row in m.get("level_connectors", []) or []
        if UNDERGROUND_LEVEL in {int(row.get("from_level", 0)), int(row.get("to_level", 0))}
    }
    missing_stairs = sorted(REQUIRED_STAIRS - set(connectors))
    if missing_stairs:
        fail(f"Missing Underground stairs: {missing_stairs}")

    for cid in sorted(REQUIRED_STAIRS):
        c = connectors[cid]
        if str(c.get("kind", "")).lower() != "stairs":
            fail(f"Underground connector {cid} is not stairs")
        from_level = int(c.get("from_level", 0))
        to_level = int(c.get("to_level", 0))
        if (from_level, to_level) != (0, UNDERGROUND_LEVEL):
            fail(f"Underground connector {cid} must be authored 0->-1, got {from_level}->{to_level}")
        start = c.get("start", [])
        end = c.get("end", [])
        if len(start) < 2 or len(end) < 2:
            fail(f"Underground connector {cid} has malformed endpoints")
        sx, sy = map(float, start[:2])
        ex, ey = map(float, end[:2])
        if blocked(sx, sy, m, level=0):
            fail(f"Surface stair entrance {cid} starts in blocked Ground geometry")
        if blocked(ex, ey, m, level=UNDERGROUND_LEVEL):
            fail(f"Underground stair landing {cid} ends in blocked level -1 geometry")
        if not point_near_road(ex, ey, m, level=UNDERGROUND_LEVEL):
            fail(f"Underground stair landing {cid} does not terminate on a level -1 road")

        dx, dy = ex - sx, ey - sy
        length = math.hypot(dx, dy)
        if length <= 0.0:
            fail(f"Underground connector {cid} has zero length")
        ux, uy = dx / length, dy / length
        step = min(8.0, length * 0.35)
        if resolve_level_transition(ex, ey, 0, m, previous_x=ex-ux*step, previous_y=ey-uy*step) != UNDERGROUND_LEVEL:
            fail(f"Underground connector {cid} does not transition Ground -> -1")
        if resolve_level_transition(sx, sy, UNDERGROUND_LEVEL, m, previous_x=sx+ux*step, previous_y=sy+uy*step) != 0:
            fail(f"Underground connector {cid} does not transition -1 -> Ground")

    # Negative-level confinement is an engine invariant: this point is far from
    # every authored Underground road and connector and must remain blocked.
    if not blocked(7600.0, 3000.0, m, level=UNDERGROUND_LEVEL):
        fail("Underground permits movement outside authored passages")

    ground_builder = (ROOT / "tools" / "build_v100_ground_approval.py").read_text(encoding="utf-8")
    if "subterranean_roads=excluded" not in ground_builder or ">= 0" not in ground_builder:
        fail("Ground approval builder does not explicitly exclude negative-level roads")

    print("V100_UNDERGROUND_SEMANTICS_OK level=-1 roads=3 stairs=3 connected=true confined=true")


if __name__ == "__main__":
    main()
