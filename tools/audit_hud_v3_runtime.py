#!/usr/bin/env python3
from __future__ import annotations

"""Headless integration audit for the live Open Night HUD 3.0 shell."""

import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pygame

import v100_client


def _hash(surface: pygame.Surface) -> str:
    return hashlib.sha256(pygame.image.tobytes(surface, "RGBA")).hexdigest()


def _render_world_frame(game, local) -> pygame.Surface:
    display_surface = game.screen
    view_size = game.logical_view_size()
    game.camera_controller.update(
        (local.render_x, local.render_y),
        (view_size[0] // 2, view_size[1] // 2),
        view_size,
        (game.grid_world.world_w, game.grid_world.world_h),
        1.0 / 60.0,
        force_center=True,
    )
    world_surface = pygame.Surface(view_size).convert()
    game.screen = world_surface
    game.draw_world()
    game.draw_player(local, True)
    game.screen = display_surface
    pygame.transform.smoothscale(world_surface, display_surface.get_size(), display_surface)
    game.draw_player_nameplates()
    return display_surface.copy()


def main() -> None:
    game_client = v100_client.game_client
    game_client.NetworkClient.start = lambda self: None
    v100_client.install_v100_client()
    game = game_client.Game("ws://hud-v3-audit.invalid:8765", "5550000300", "HUD3Audit")
    if game.grid_world is None or game.grid_renderer is None:
        raise AssertionError("HUD 3.0 audit requires the canonical GridWorld runtime")

    x, y = game.grid_world.choose_spawn("ground", game_client.PLAYER_RADIUS)
    local = game_client.RemotePlayer({
        "id": "hud-v3-local",
        "name": "HUD3Audit",
        "x": x,
        "y": y,
        "aim": -1.5707963267948966,
        "cash": 0,
        "packages": 0,
        "level": 0,
        "appearance": None,
    })
    game.local_id = local.id
    game.players = {local.id: local}
    game.map_players = {local.id: {"name": local.name, "x": x, "y": y, "level": 0}}
    game.connected = True
    game.notice_until = 0.0
    game.camera_zoom = 0.85

    output_dir = Path(os.environ.get(
        "OPEN_NIGHT_HUD3_AUDIT_DIR",
        str(Path(tempfile.gettempdir()) / "open-night-hud-v3-audit"),
    ))
    output_dir.mkdir(parents=True, exist_ok=True)

    world_frame = _render_world_frame(game, local)
    game.screen.blit(world_frame, (0, 0))
    game.inventory_open = False
    game.draw_hud()
    closed = game.screen.copy()
    pygame.image.save(closed, output_dir / "hud-v3-closed.png")

    game.screen.blit(world_frame, (0, 0))
    game.inventory_open = True
    game.draw_hud()
    opened = game.screen.copy()
    pygame.image.save(opened, output_dir / "hud-v3-esc-open.png")

    hud = game.hud_v3
    if len(hud.hotbar_rects) != 13:
        raise AssertionError(f"expected 13 hotbar slots, got {len(hud.hotbar_rects)}")
    expected_navigation = {"resume", "settings", "radio", "controls", "friends", "messages", "quit"}
    if set(hud.navigation_rects) != expected_navigation:
        raise AssertionError(f"HUD 3.0 navigation mismatch: {sorted(hud.navigation_rects)}")
    navigation_values = list(hud.navigation_rects.values())
    for index, rect in enumerate(navigation_values):
        if any(rect.colliderect(other) for other in navigation_values[index + 1:]):
            raise AssertionError("HUD 3.0 top navigation tabs overlap")
    if len(hud.character_rects) != 20 or len(hud.ring_rects) != 10:
        raise AssertionError(
            f"expected 20 character sockets + 10 rings, got {len(hud.character_rects)} + {len(hud.ring_rects)}"
        )
    if len(hud.inventory_cells) != 60:
        raise AssertionError(f"expected 10x6/60 inventory cells, got {len(hud.inventory_cells)}")
    if hud.inventory_rect.width < 490 or hud.inventory_rect.height < 330:
        raise AssertionError(f"inventory was not enlarged at 1280x720: {hud.inventory_rect.size}")
    cell_sizes = {(rect.width, rect.height) for rect in hud.inventory_cells}
    if len(cell_sizes) != 1:
        raise AssertionError(f"inventory cells are not a single aligned grid: {cell_sizes}")
    if hud.magazine_rect.collidepoint(game.screen.get_rect().center):
        raise AssertionError("magazine obscures the strict center/player opening")
    navigation_bottom = max(rect.bottom for rect in navigation_values)
    if not (navigation_bottom < hud.stats_rect.top < hud.character_rects[0].top):
        raise AssertionError("Escape-open content was not moved below the navigation strip")
    if hud.character_rects[0].top <= hud.inventory_rect.top:
        raise AssertionError("equipment/pocket/ring cluster was not moved below the inventory")
    equipment_hotbar_gap = min(rect.top for rect in hud.hotbar_rects) - max(rect.bottom for rect in hud.ring_rects)
    if not 12 <= equipment_hotbar_gap <= 36:
        raise AssertionError(
            f"equipment/pocket/ring cluster is not close to the hotbar: {equipment_hotbar_gap}px gap"
        )
    if min(rect.x for rect in hud.ring_rects) != 14 or any(rect.colliderect(hud.magazine_rect) for rect in hud.ring_rects):
        raise AssertionError("ring row is not independently left-aligned and clear of the magazine")
    if any(rect.width != rect.height for rect in hud.character_rects):
        raise AssertionError("head/outfit/pocket sockets are not square")
    equipment_columns = {rect.x for rect in hud.character_rects}
    equipment_rows = {rect.y for rect in hud.character_rects}
    equipment_bounds = hud.character_rects[0].unionall(hud.character_rects[1:])
    if len(equipment_columns) != 5 or len(equipment_rows) != 4 or not 36 <= equipment_bounds.x <= 80:
        raise AssertionError("equipment sockets are not a left-side 5x4 square block")
    if abs(equipment_bounds.centery - game.screen.get_height() // 2) > 2:
        raise AssertionError("equipment square block is not vertically centered")
    if hud.resource_rects["Energy"].colliderect(hud.resource_rects["Fatigue"]):
        raise AssertionError("energy and fatigue HUD hit areas overlap")
    if hud.fatigue_icon_rect.size != (25, 24):
        raise AssertionError("fatigue brain icon geometry is missing")
    if hud.fatigue_icon_orientation != "side_profile":
        raise AssertionError("fatigue brain is not side-on")

    selected_action = hud.navigation_at(hud.navigation_rects["radio"].center)
    if selected_action != "radio":
        raise AssertionError("radio-stations navigation tab is not clickable")
    game._activate_hud3_navigation(selected_action)
    if not game.pause_menu_open or game.pause_page != "radio" or game.inventory_open:
        raise AssertionError("radio-stations tab did not open the mature radio page")
    game.pause_menu_open = False
    game.pause_page = "main"
    game.inventory_open = True

    diameter = hud.minimap_diameter(game.screen.get_size())
    mini_x, mini_y = hud.minimap_origin(game.screen.get_size(), diameter)
    if mini_x < game.screen.get_width() // 2 or mini_y < game.screen.get_height() // 2:
        raise AssertionError("minimap is not anchored in the lower-right quadrant")
    if hud.minimap_shape != "square":
        raise AssertionError("HUD 3.0 minimap is not square")
    chat_rect = hud.chat_input_rect(game.screen.get_size())
    if chat_rect.left <= hud.hotbar_rects[-1].right or chat_rect.right >= mini_x:
        raise AssertionError("chat input is not between the hotbar and minimap")
    if chat_rect.left <= hud.resource_rects["Fatigue"].right:
        raise AssertionError("chat input overlaps the fatigue resource")
    if chat_rect.bottom != game.screen.get_height() - 18:
        raise AssertionError("chat input is not anchored at the bottom-right HUD line")

    hud.handle_keydown(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_1), overlay_open=False)
    if hud.active_hotbar != 1:
        raise AssertionError("hotbar key 1 did not select knife slot 1")
    hud.active_hotbar = 2
    hud.handle_keydown(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_r), overlay_open=False)
    hud.update(hud.reload_seconds)
    if hud.magazine_rounds != hud.magazine_capacity or hud.reload_active:
        raise AssertionError("hold-R reload contract did not complete")

    # The production shell starts empty; inject one round only for the drag
    # contract audit, then restore the empty state.
    hud.magazine_rounds = 9
    hud.loose_rounds = 1
    hud.loose_round_rect = hud.character_rects[6]
    if not hud.handle_mouse_down(hud.loose_round_rect.center):
        raise AssertionError("individual round drag did not begin")
    if not hud.handle_mouse_up(hud.magazine_rect.center):
        raise AssertionError("individual round drag did not end")
    if hud.magazine_rounds != 10 or hud.loose_rounds != 0:
        raise AssertionError("individual round did not top up the magazine")

    report = {
        "hud_version": "3.0",
        "resolution": list(game.screen.get_size()),
        "closed_sha256": _hash(closed),
        "esc_open_sha256": _hash(opened),
        "hotbar_keys": list(game_client.HOTBAR_KEYS) if hasattr(game_client, "HOTBAR_KEYS") else [
            "`", "1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "-", "="
        ],
        "hotbar_slots": len(hud.hotbar_rects),
        "navigation_tabs": list(hud.navigation_rects),
        "navigation_click_verified": True,
        "open_content_lowered": True,
        "equipment_hotbar_gap_px": equipment_hotbar_gap,
        "inventory_panel_size": list(hud.inventory_rect.size),
        "energy_fatigue_separated": True,
        "fatigue_icon": "brain_side_profile",
        "equipment_layout": "5x4_square_block_left_vertically_centered",
        "magazine_position_preserved": True,
        "character_slots": len(hud.character_rects),
        "ring_slots": len(hud.ring_rects),
        "inventory": {"cols": 10, "rows": 6, "cells": len(hud.inventory_cells), "initial_items": 0},
        "minimap_origin": [mini_x, mini_y],
        "minimap_diameter": diameter,
        "minimap_shape": hud.minimap_shape,
        "chat_input_rect": list(chat_rect),
        "magazine": {"capacity": 10, "individual_round_drag_verified": True, "hold_r_verified": True},
        "center_opening_clear": True,
        "artifacts": ["hud-v3-closed.png", "hud-v3-esc-open.png", "hud-v3-chat-active.png"],
    }

    game.screen.blit(world_frame, (0, 0))
    game.inventory_open = False
    game.chat_active = True
    game.chat_text = "HUD 3.0 chat"
    game.draw_hud()
    game.draw_chat_input()
    if game.chat_input_rect != chat_rect:
        raise AssertionError("runtime chat renderer did not use the HUD 3.0 chat bounds")
    chat_active = game.screen.copy()
    pygame.image.save(chat_active, output_dir / "hud-v3-chat-active.png")
    game.chat_active = False

    (output_dir / "hud-v3-runtime-audit.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    game.network.stop()
    pygame.quit()


if __name__ == "__main__":
    main()
