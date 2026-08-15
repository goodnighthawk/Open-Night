from __future__ import annotations

from pathlib import Path
import math
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from common import (
    PLAYER_RADIUS,
    PlayerState,
    blocked,
    point_near_level_connector,
    point_near_road,
    resolve_level_transition,
)
from mapfiles.loader import load_map_folder

MAP_DIR = ROOT / "mapfiles" / "data" / "map_001_gwb_corridor"

m = load_map_folder(MAP_DIR)
levels = {int(row.get("id", 0)): row for row in m.get("levels", []) or []}
connectors = m.get("level_connectors", []) or []
roads = m.get("roads", []) or []
walkable_levels = {lid for lid, row in levels.items() if bool(row.get("walkable", True))}

if len(walkable_levels) < 2:
    raise SystemExit(f"Expected at least 2 walkable outdoor levels, found {sorted(walkable_levels)}")
if 0 not in walkable_levels:
    raise SystemExit("Ground Level 0 is missing or not walkable")
if not connectors:
    raise SystemExit("No level connectors are authored")

world_w, world_h = float(m["world_w"]), float(m["world_h"])
for c in connectors:
    fid, tid = int(c.get("from_level", 0)), int(c.get("to_level", 0))
    if fid not in levels or tid not in levels:
        raise SystemExit(f"Connector {c.get('id')} references missing levels {fid}->{tid}")
    a, b = c.get("start", []), c.get("end", [])
    if len(a) < 2 or len(b) < 2:
        raise SystemExit(f"Connector {c.get('id')} has malformed endpoints")
    for label, p in (("start", a), ("end", b)):
        x, y = map(float, p[:2])
        if not (0 <= x <= world_w and 0 <= y <= world_h):
            raise SystemExit(f"Connector {c.get('id')} {label} is out of bounds: {p}")

    # Endpoint switch contract: from-level reaches the to endpoint; reverse
    # traversal reaches the from endpoint before the level switches back.
    if resolve_level_transition(float(b[0]), float(b[1]), fid, m) != tid:
        raise SystemExit(f"Connector {c.get('id')} does not transition {fid}->{tid} at its end")
    if resolve_level_transition(float(a[0]), float(a[1]), tid, m) != fid:
        raise SystemExit(f"Connector {c.get('id')} does not transition {tid}->{fid} at its start")
    sx, sy = float(a[0]), float(a[1])
    ex, ey = float(b[0]), float(b[1])
    dx, dy = ex - sx, ey - sy
    length = math.hypot(dx, dy)
    if length <= 0.001:
        raise SystemExit(f"Connector {c.get('id')} has coincident endpoints")
    ux, uy = dx / length, dy / length

    # Runtime direction contract: entering the far endpoint while moving
    # forward ascends; continuing forward or standing cannot bounce back; a
    # reverse movement at an overlapping compact connector may descend
    # immediately. Longer ramps descend once their lower endpoint is reached.
    step = min(8.0, length * 0.4)
    if resolve_level_transition(
        ex, ey, fid, m, previous_x=ex - ux * step, previous_y=ey - uy * step
    ) != tid:
        raise SystemExit(f"Connector {c.get('id')} ignores forward traversal direction")
    if resolve_level_transition(
        ex, ey, tid, m, previous_x=ex - ux * step, previous_y=ey - uy * step
    ) != tid:
        raise SystemExit(f"Connector {c.get('id')} bounces down while movement continues forward")
    if resolve_level_transition(ex, ey, tid, m, previous_x=ex, previous_y=ey) != tid:
        raise SystemExit(f"Connector {c.get('id')} flickers while the player is stationary")
    reverse_x, reverse_y = ex - ux * step, ey - uy * step
    expected_reverse_level = (
        fid
        if math.hypot(reverse_x - sx, reverse_y - sy)
        <= max(24.0, min(72.0, float(c.get("width", 80)) * 0.42))
        else tid
    )
    if resolve_level_transition(
        reverse_x,
        reverse_y,
        tid,
        m,
        previous_x=ex,
        previous_y=ey,
    ) != expected_reverse_level:
        raise SystemExit(f"Connector {c.get('id')} does not respond correctly to immediate reversal")
    mx, my = (float(a[0])+float(b[0]))*.5, (float(a[1])+float(b[1]))*.5
    if not point_near_level_connector(mx, my, m, level=fid):
        raise SystemExit(f"Connector {c.get('id')} is not walkable from level {fid}")
    if not point_near_level_connector(mx, my, m, level=tid):
        raise SystemExit(f"Connector {c.get('id')} is not walkable from level {tid}")

# Every positive walkable road level must have a connector path to another level.
for road in roads:
    level = int(road.get("level", 0) or 0)
    if level <= 0 or not bool(road.get("walkable", True)):
        continue
    if not any(level in {int(c.get("from_level", 0)), int(c.get("to_level", 0))} for c in connectors):
        raise SystemExit(f"Elevated walkable road {road.get('id')} on level {level} has no connector")
    pts = road.get("points", []) or []
    if len(pts) >= 2:
        a, b = pts[len(pts)//2-1], pts[len(pts)//2]
        mx, my = (float(a[0])+float(b[0]))*.5, (float(a[1])+float(b[1]))*.5
        if not point_near_road(mx, my, m, level=level):
            raise SystemExit(f"Road {road.get('id')} fails same-level corridor lookup")
        if blocked(mx, my, m, level=level):
            raise SystemExit(f"Walkable elevated road {road.get('id')} is blocked at its midpoint")

# A non-ground player cannot leave all authored elevated surfaces.
probe = (PLAYER_RADIUS * 3.0, PLAYER_RADIUS * 3.0)
for level in sorted(l for l in walkable_levels if l != 0):
    if not blocked(probe[0], probe[1], m, level=level):
        raise SystemExit(f"Level {level} permits free-floating movement away from roads/connectors")

p = PlayerState("audit", "Audit", 100.0, 100.0, level=max(walkable_levels))
if p.public_dict().get("level") != max(walkable_levels):
    raise SystemExit("PlayerState public snapshot does not include authoritative level")

server_src = (ROOT / "server.py").read_text(encoding="utf-8")
client_src = (ROOT / "client.py").read_text(encoding="utf-8")
viewer_src = (ROOT / "map_viewer.py").read_text(encoding="utf-8")
for token in ("resolve_level_transition", "previous_x=movement_start_x", "previous_y=movement_start_y", "level=current_level", "move_with_collisions"):
    if token not in server_src:
        raise SystemExit(f"Server multi-level integration missing token: {token}")
for token in ("next_level != previous_level", "LAYER_TRANSITION_JUMP_SECONDS", "session.jump_until = max"):
    if token not in server_src:
        raise SystemExit(f"Server automatic layer-jump integration missing token: {token}")
if "self.level = int(float(data.get(\"level\"" not in client_src:
    raise SystemExit("Client RemotePlayer does not consume level snapshots")
if "draw_elevated_overlay" not in client_src:
    raise SystemExit("Client does not perform elevated-deck dynamic occlusion")
for token in ("jump_scale_multiplier", "jump_lift_px", "render_scale *="):
    if token not in client_src:
        raise SystemExit(f"Client visible jump scaling is missing: {token}")
if "K_LEFTBRACKET" not in viewer_src or "self.levels" not in viewer_src:
    raise SystemExit("Map Viewer does not dynamically cycle authored levels")

print("Multi-level map/runtime audit: PASS")
print(f"walkable levels={sorted(walkable_levels)} connectors={len(connectors)} elevated roads={sum(int(r.get('level',0) or 0)>0 for r in roads)}")
print("authoritative player level + automatic connector jump + elevated collision confinement + viewer level cycling verified")
