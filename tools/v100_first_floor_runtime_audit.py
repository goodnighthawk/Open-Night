#!/usr/bin/env python3
"""Audit v1.0 world-registered First Floor semantics and runtime rendering.

Run after ``wire_v100_first_floor_runtime.py``. The audit uses the real Map 001
CSV loader, PlayerState serialization, continuous interior collision model and
headless Pygame renderer. It deliberately fails if the legacy independent
isometric projection reappears.
"""
from __future__ import annotations

import math
import os
import sys
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pygame

from common import PlayerState
from interior_art import IsometricInterior
from interior_layout import (
    EXIT_TILE,
    START_TILE,
    blocked_tiles,
    blocked_world_rects,
    building_rect,
    interior_building_id,
    interior_exit_world,
    interior_floor_rect,
    interior_move_world,
    interior_start_world,
    point_walkable,
)
from mapfiles.loader import load_map_folder

MAP_DIR = ROOT / "mapfiles/data/map_001_gwb_corridor"
PREVIEW_DIR = ROOT / "assets/environment/approved/map_001_gwb_corridor/v100_layers/first_floor/night"
CONTACT_SHEET = ROOT / "assets/environment/approved/map_001_gwb_corridor/v100_layers/FIRST_FLOOR_PLAYER_SCALE_PREVIEW.png"
EXPECTED_INTERIORS = {
    "starter_apartment", "corner_shop", "night_diner", "pharmacy", "laundromat",
    "pawn_shop", "garage", "nightclub", "warehouse_office", "rooftop_loft",
}


def fail(message: str) -> None:
    raise SystemExit(message)


def contains_rect(inner, outer, eps: float = 1e-5) -> bool:
    ix, iy, iw, ih = inner
    ox, oy, ow, oh = outer
    return (
        ix >= ox - eps and iy >= oy - eps and
        ix + iw <= ox + ow + eps and iy + ih <= oy + oh + eps
    )


def source_contract_checks() -> None:
    interior_art = (ROOT / "interior_art.py").read_text(encoding="utf-8")
    client = (ROOT / "client.py").read_text(encoding="utf-8")
    server = (ROOT / "server.py").read_text(encoding="utf-8")
    common = (ROOT / "common.py").read_text(encoding="utf-8")
    loader = (ROOT / "mapfiles/loader.py").read_text(encoding="utf-8")

    # Test executable/projection markers, not explanatory prose. Comments may
    # legitimately describe the removed renderer; the runtime must not contain
    # an isometric transform or the old diamond-grid constants/calls.
    forbidden = (
        "def iso(",
        "TILE_W = 64",
        "TILE_H = 32",
        "self.iso(",
        "iso_x =",
        "iso_y =",
    )
    for marker in forbidden:
        if marker in interior_art:
            fail(f"Legacy isometric runtime marker present: {marker}")
    required_art = (
        "world-registered First Floor renderer",
        "interior_floor_rect(self.map_config",
        'mode="topdown"',
        "FIRST FLOOR · WORLD REGISTERED",
    )
    for marker in required_art:
        if marker not in interior_art:
            fail(f"First Floor renderer marker missing: {marker}")

    required_client = (
        "IsometricInterior(self.map_config)",
        "self.interior.set_map(self.map_config)",
        'self.network.send({"type": "interior_move", "dx": ix, "dy": iy})',
        "Movement is sampled continuously in send_input()",
        "float(message.get(\"x\", 0.0) or 0.0)",
    )
    for marker in required_client:
        if marker not in client:
            fail(f"First Floor client marker missing: {marker}")

    required_server = (
        "interior_start_world(ACTIVE_MAP, player.interior_id)",
        "nx, ny, aim = interior_move_world(",
        "dx, dy = float(message.get(\"dx\", 0.0)), float(message.get(\"dy\", 0.0))",
        '"x": round(float(player.interior_x), 2)',
    )
    for marker in required_server:
        if marker not in server:
            fail(f"First Floor server marker missing: {marker}")
    if "interior_step(" in server or "INTERIOR_START_TILE" in server:
        fail("Server still uses detached grid interior movement")
    if "interior_x: float = 0.0" not in common or '"interior_x": round(float(self.interior_x), 2)' not in common:
        fail("PlayerState does not serialize world-space First Floor coordinates")
    if '"building_id": str(r.get("building_id", ""))' not in loader:
        fail("Map loader does not preserve explicit interior building binding")


def semantic_checks(m: dict) -> list[dict]:
    interiors = list(m.get("interiors", []) or [])
    ids = {str(row.get("id", "")) for row in interiors}
    missing = sorted(EXPECTED_INTERIORS - ids)
    if missing:
        fail(f"Expected First Floor interiors missing: {missing}")

    # Verify every explicit interior binds to the exact authored building and to
    # a building that declares a walkable local first-floor/upper layer.
    layers_by_building: dict[str, list[dict]] = {}
    for row in m.get("building_layers", []) or []:
        layers_by_building.setdefault(str(row.get("building_id", "")), []).append(row)

    checked = []
    for info in interiors:
        room_id = str(info.get("id", ""))
        if room_id not in EXPECTED_INTERIORS:
            continue
        explicit = str(info.get("building_id", "")).strip()
        if not explicit:
            fail(f"Interior {room_id} lost its authored building_id")
        resolved = interior_building_id(m, room_id)
        if resolved != explicit:
            fail(f"Interior {room_id} resolved {resolved}, expected explicit {explicit}")
        outer = building_rect(m, resolved)
        floor = interior_floor_rect(m, room_id)
        if outer is None or floor is None:
            fail(f"Interior {room_id} has no registered building/floor rectangle")
        if not contains_rect(floor, outer):
            fail(f"Interior {room_id} floor escaped building footprint: floor={floor} building={outer}")

        upper = [row for row in layers_by_building.get(resolved, []) if int(row.get("level_id", -99)) == 1]
        if not upper or not any(bool(row.get("walkable", False)) for row in upper):
            fail(f"Interior {room_id} building {resolved} lacks walkable local First Floor declaration")

        sx, sy = interior_start_world(m, room_id)
        ex, ey = interior_exit_world(m, room_id)
        if not point_walkable(m, room_id, sx, sy):
            fail(f"Interior {room_id} spawn is blocked")
        # Exit tile center is reserved by the furniture template. It must be
        # inside the floor even if wall-clearance makes the precise point a door
        # threshold rather than a generic walkable point.
        fx, fy, fw, fh = floor
        if not (fx <= ex <= fx + fw and fy <= ey <= fy + fh):
            fail(f"Interior {room_id} exit escaped registered floor")
        if START_TILE in blocked_tiles(room_id) or EXIT_TILE in blocked_tiles(room_id):
            fail(f"Interior {room_id} reserved spawn/exit cell remains furniture-blocked")

        # Each furniture collision rectangle must remain fully in the registered
        # floor; otherwise the visual/collision authoring transform disagrees.
        for rect in blocked_world_rects(m, room_id):
            if not contains_rect(rect, floor):
                fail(f"Interior {room_id} furniture collision escaped floor: {rect}")

        # Prove movement is continuous world space: repeated normalized input
        # samples must move by sub-cell pixel distances and never enter furniture.
        x, y = sx, sy
        moved = 0.0
        for _ in range(8):
            nx, ny, _ = interior_move_world(m, room_id, x, y, 1.0, 0.0)
            delta = math.hypot(nx - x, ny - y)
            if delta > 0:
                moved += delta
                if delta > 10.1:
                    fail(f"Interior {room_id} client sample exceeded authoritative step cap: {delta}")
                if not point_walkable(m, room_id, nx, ny):
                    fail(f"Interior {room_id} moved into blocked space")
            x, y = nx, ny
        if moved <= 0.0:
            # Some presets may block immediately to the east; try north without
            # weakening collision semantics.
            x, y = sx, sy
            for _ in range(8):
                nx, ny, _ = interior_move_world(m, room_id, x, y, 0.0, -1.0)
                moved += math.hypot(nx - x, ny - y)
                x, y = nx, ny
        if moved <= 0.0:
            fail(f"Interior {room_id} spawn cannot move continuously in either test direction")
        checked.append(info)

    # Network serialization must preserve actual world-space decimals, not cast
    # back to 10x8 integer cells.
    p = PlayerState("audit", "Audit", 0.0, 0.0, interior_id="starter_apartment", interior_x=1234.56, interior_y=2345.67)
    public = p.public_dict()
    if public.get("interior_x") != 1234.56 or public.get("interior_y") != 2345.67:
        fail(f"PlayerState rounded First Floor world coordinates incorrectly: {public}")
    return checked


def render_checks(m: dict, interiors: list[dict]) -> None:
    pygame.init()
    pygame.display.set_mode((1, 1))
    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    contact = pygame.Surface((1280, 720))
    contact.fill((5, 7, 9))
    font = pygame.font.Font(None, 30)
    small = pygame.font.Font(None, 20)
    renderer = IsometricInterior(m)
    if hasattr(renderer, "iso"):
        fail("First Floor renderer still exposes an isometric projection method")

    try:
        thumb_w, thumb_h = 256, 360
        for index, info in enumerate(interiors[:10]):
            room_id = str(info["id"])
            renderer.enter(room_id, str(info.get("name", room_id)))
            sx, sy = interior_start_world(m, room_id)
            renderer.set_player_state(sx, sy, -math.pi / 2.0)
            surface = pygame.Surface((1280, 720))
            renderer.draw(surface, font, small, appearance=None, occupants=[])
            # Production-scale artifact for the first representative room.
            if index == 0:
                pygame.image.save(surface, str(PREVIEW_DIR / "starter_apartment_1280x720.png"))
            raw = pygame.image.tostring(surface, "RGB")
            if len(set(raw[::997])) < 3:
                fail(f"First Floor render for {room_id} appears blank/flat")
            thumb = pygame.transform.smoothscale(surface, (thumb_w, thumb_h))
            contact.blit(thumb, ((index % 5) * thumb_w, (index // 5) * thumb_h))
        pygame.image.save(contact, str(CONTACT_SHEET))
    finally:
        pygame.quit()


def main() -> None:
    source_contract_checks()
    m = load_map_folder(MAP_DIR)
    checked = semantic_checks(m)
    render_checks(m, checked)
    print(
        "V100_FIRST_FLOOR_RUNTIME_OK "
        f"interiors={len(checked)} coordinates=world_xy projection=orthographic "
        f"continuous=true furniture_collision=registered preview={CONTACT_SHEET.name}"
    )


if __name__ == "__main__":
    main()
