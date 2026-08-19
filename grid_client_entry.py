from __future__ import annotations

"""v1.0 grid-authoritative desktop client entry.

The mature legacy client remains the feature implementation library, but v1.0
has exactly one exterior map authority: GridWorld.  Ground rendering, minimap
geometry and the M world map all derive from the tile grid.  Legacy map metadata
may still contribute human-readable place names while its roads/buildings/water
are never drawn into the v1.0 exterior UI.
"""

import asyncio
import math

import pygame

import client as game_client


_ORIGINAL_DRAW_WORLD = game_client.Game.draw_world
_ORIGINAL_DRAW_PLAYER = game_client.Game.draw_player
_ORIGINAL_DRAW_NAMEPLATES = game_client.Game.draw_player_nameplates


def _grid_map_authority_available(game: game_client.Game) -> bool:
    """Return whether v1.0's one permitted map authority is ready."""
    return getattr(game, "grid_renderer", None) is not None and getattr(game, "grid_world", None) is not None


def _grid_ground_active(game: game_client.Game) -> bool:
    if not _grid_map_authority_available(game):
        return False
    local = game.players.get(game.local_id or "")
    level = int(getattr(local, "level", 0)) if local is not None else 0
    return level == 0


def _draw_world_grid_exclusive(game: game_client.Game) -> None:
    """Render exactly one Ground authority when the v1.0 grid is active."""
    if not _grid_ground_active(game):
        _ORIGINAL_DRAW_WORLD(game)
        return
    game.grid_renderer.draw_view(game.screen, game.camera(), "ground")


def _with_grid_player_scale(game: game_client.Game, callback, *args, **kwargs):
    if not _grid_ground_active(game):
        return callback(game, *args, **kwargs)
    render = game.settings.setdefault("render", {})
    previous = render.get("player_scale", 1)
    # The legacy avatar was authored for the old small vector-map scale. At the
    # 256 px v1.0 tile scale, 2x restores the intended player-to-street ratio.
    render["player_scale"] = max(2, int(previous or 1))
    try:
        return callback(game, *args, **kwargs)
    finally:
        render["player_scale"] = previous


def _draw_player_grid_scale(game: game_client.Game, player, local: bool) -> None:
    return _with_grid_player_scale(game, _ORIGINAL_DRAW_PLAYER, player, local)


def _draw_nameplates_grid_scale(game: game_client.Game) -> None:
    return _with_grid_player_scale(game, _ORIGINAL_DRAW_NAMEPLATES)


def _build_grid_world_map_cache(game: game_client.Game, width: int, height: int):
    """Build the M-map background from the actual GridRenderer, never legacy geometry."""
    if not _grid_map_authority_available(game):
        raise RuntimeError("GridWorld map authority unavailable")

    world = game.grid_world
    width = max(64, int(width))
    height = max(64, int(height))
    tile_px = max(1, min(width // world.width, height // world.height))
    draw_w = world.width * tile_px
    draw_h = world.height * tile_px
    surface = pygame.Surface((draw_w, draw_h)).convert()
    game.grid_renderer.draw_overview(surface, "ground")

    pygame.draw.rect(surface, (108, 111, 104), surface.get_rect(), width=1)
    return surface, float(world.world_w), float(world.world_h)


def _grid_map_point(map_rect: pygame.Rect, world, x: float, y: float) -> tuple[int, int] | None:
    try:
        x = float(x)
        y = float(y)
    except (TypeError, ValueError):
        return None
    if not (math.isfinite(x) and math.isfinite(y)):
        return None
    if x < 0.0 or y < 0.0 or x > world.world_w or y > world.world_h:
        return None
    return (
        int(map_rect.x + x / world.world_w * map_rect.width),
        int(map_rect.y + y / world.world_h * map_rect.height),
    )


def _draw_grid_world_map_impl(game: game_client.Game) -> None:
    """Full M map using GridWorld art plus dynamic gameplay markers only."""
    if not _grid_map_authority_available(game):
        game.screen.fill((12, 12, 14))
        message = game.big_font.render("GRID MAP UNAVAILABLE", True, game_client.TEXT_COLOR)
        game.screen.blit(message, message.get_rect(center=game.screen.get_rect().center))
        return

    sw, sh = game.screen.get_size()
    if sw < 220 or sh < 180:
        msg = game.small_font.render("Window too small for world map - resize or press M", True, game_client.TEXT_COLOR)
        game.screen.blit(msg, (10, 10))
        return

    shade = pygame.Surface((sw, sh), pygame.SRCALPHA)
    shade.fill((0, 0, 0, 205))
    game.screen.blit(shade, (0, 0))

    margin_x = min(42, max(10, sw // 20))
    margin_y = min(38, max(10, sh // 20))
    panel = pygame.Rect(margin_x, margin_y, max(200, sw - 2 * margin_x), max(160, sh - 2 * margin_y))
    panel.clamp_ip(game.screen.get_rect())
    pygame.draw.rect(game.screen, (20, 23, 24), panel, border_radius=9)
    pygame.draw.rect(game.screen, (88, 92, 93), panel, width=2, border_radius=9)
    title = game.big_font.render("OPEN NIGHT — GRID WORLD", True, game_client.TEXT_COLOR)
    game.screen.blit(title, (panel.x + 18, panel.y + 12))
    subtitle = game.small_font.render(
        "M close | yellow: you | green: friends | blue: players | map geometry: v1.0 tiles",
        True, game_client.MUTED_TEXT,
    )
    game.screen.blit(subtitle, (panel.x + 20, panel.y + 46))

    available = pygame.Rect(panel.x + 20, panel.y + 72, max(64, panel.width - 40), max(64, panel.height - 102))
    world = game.grid_world
    cache_key = ("grid-v100", world.width, world.height, world.cell_px, available.width, available.height)
    if game._world_map_cache is None or game._world_map_cache_key != cache_key:
        game._world_map_cache = _build_grid_world_map_cache(game, available.width, available.height)
        game._world_map_cache_key = cache_key

    map_surface, _world_w, _world_h = game._world_map_cache
    map_rect = map_surface.get_rect(center=available.center)
    game.screen.blit(map_surface, map_rect)

    local = game.players.get(game.local_id or "")
    if local is not None:
        p = _grid_map_point(map_rect, world, local.render_x, local.render_y)
        if p is not None:
            pygame.draw.circle(game.screen, (12, 13, 13), p, 7)
            pygame.draw.circle(game.screen, game_client.LOCAL_COLOR, p, 5)

    # Preserve job-economy destinations as gameplay markers. They are not map
    # geometry and can be migrated to grid-associated records independently.
    for raw_pos, marker_color, marker_label in (
        (game.map_config.get("supplier_pos", game_client.SUPPLIER_POS), game_client.SUPPLIER_COLOR, "SUPPLIER"),
        (game.map_config.get("customer_pos", game_client.CUSTOMER_POS), game_client.CUSTOMER_COLOR, "BUYER"),
    ):
        try:
            p = _grid_map_point(map_rect, world, raw_pos[0], raw_pos[1])
        except (TypeError, IndexError, KeyError):
            p = None
        if p is None:
            continue
        pygame.draw.circle(game.screen, (12, 13, 13), p, 8)
        pygame.draw.circle(game.screen, marker_color, p, 6)
        label = game.tiny_font.render(marker_label, True, marker_color)
        label_rect = label.get_rect(midleft=(p[0] + 8, p[1]))
        pygame.draw.rect(game.screen, (18, 21, 22), label_rect.inflate(4, 2), border_radius=2)
        game.screen.blit(label, label_rect)

    for pid, marker in game.map_players.items():
        if pid == game.local_id:
            continue
        live = game.players.get(pid)
        px = live.render_x if live is not None else marker.get("x", 0.0)
        py = live.render_y if live is not None else marker.get("y", 0.0)
        p = _grid_map_point(map_rect, world, px, py)
        if p is None:
            continue
        name = str(marker.get("name", "Player"))[:18]
        friend = game.is_friend(name)
        marker_color = (112, 225, 157) if friend else game_client.REMOTE_COLOR
        pygame.draw.circle(game.screen, (12, 13, 13), p, 7 if friend else 6)
        pygame.draw.circle(game.screen, marker_color, p, 5 if friend else 4)
        label_text = f"★ {name}" if friend else name
        level = int(marker.get("level", 0) or 0)
        if level:
            label_text += f" L{level}"
        label = game.tiny_font.render(label_text, True, marker_color)
        label_rect = label.get_rect(midleft=(p[0] + 7, p[1]))
        pygame.draw.rect(game.screen, (18, 21, 22), label_rect.inflate(4, 2), border_radius=2)
        game.screen.blit(label, label_rect)

    status = game.small_font.render(
        f"Grid {world.width}x{world.height} | {world.cell_px}px cells | Ground/Roof registered | legacy geometry OFF",
        True, game_client.TEXT_COLOR,
    )
    game.screen.blit(status, (panel.x + 20, panel.bottom - 24))


def _minimap_tile_color(game: game_client.Game, tile) -> tuple[int, int, int]:
    ui = game.art_style.get("ui", {})
    env = game.art_style.get("environment", {})
    collision = str(tile.collision)
    kind = str(tile.kind)
    if collision == "road" or kind == "road":
        return tuple(ui.get("minimap_road", (110, 112, 107)))
    if "water" in kind or collision == "water":
        return tuple(ui.get("minimap_water", env.get("water", (47, 72, 84))))
    if kind in {"building", "building_footprint"} or collision == "blocked":
        return (49, 52, 52)
    if collision in {"sidewalk", "transition", "interior"} or kind in {"sidewalk", "curb", "curb_corner", "plaza"}:
        return (131, 134, 130)
    return tuple(ui.get("minimap_background", (54, 58, 56)))


def _draw_grid_local_minimap(game: game_client.Game) -> None:
    """Circular minimap whose geometry comes only from GridWorld cells."""
    if not _grid_map_authority_available(game):
        return
    local = game.players.get(game.local_id or "")
    if local is None:
        return

    ui = game.art_style.get("ui", {})
    diameter = 194
    radius = diameter // 2
    world_radius = 1050.0 if getattr(local, "in_vehicle", False) else 760.0
    scale = radius / world_radius
    mini = pygame.Surface((diameter, diameter), pygame.SRCALPHA)
    panel = tuple(ui.get("minimap_background", (54, 58, 56)))
    border = tuple(ui.get("minimap_border", (27, 28, 27)))
    mini.fill((*panel, 235))

    world = game.grid_world
    cell = world.cell_px
    gx0 = max(0, int((local.render_x - world_radius) // cell))
    gy0 = max(0, int((local.render_y - world_radius) // cell))
    gx1 = min(world.width - 1, int((local.render_x + world_radius) // cell))
    gy1 = min(world.height - 1, int((local.render_y + world_radius) // cell))
    for gy in range(gy0, gy1 + 1):
        for gx in range(gx0, gx1 + 1):
            tile = world.tile("ground", gx, gy)
            x0 = int(radius + (gx * cell - local.render_x) * scale)
            y0 = int(radius + (gy * cell - local.render_y) * scale)
            x1 = int(radius + ((gx + 1) * cell - local.render_x) * scale)
            y1 = int(radius + ((gy + 1) * cell - local.render_y) * scale)
            rect = pygame.Rect(x0, y0, max(1, x1 - x0 + 1), max(1, y1 - y0 + 1))
            pygame.draw.rect(mini, _minimap_tile_color(game, tile), rect)

    # Circular crop after tile geometry, before dynamic markers.
    circle_mask = pygame.Surface((diameter, diameter), pygame.SRCALPHA)
    pygame.draw.circle(circle_mask, (255, 255, 255, 255), (radius, radius), radius - 3)
    mini.blit(circle_mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    pygame.draw.circle(mini, border, (radius, radius), radius - 2, width=7)

    def marker_point(x: float, y: float) -> tuple[int, int] | None:
        dx = float(x) - local.render_x
        dy = float(y) - local.render_y
        if dx * dx + dy * dy > (world_radius * 0.94) ** 2:
            return None
        return int(radius + dx * scale), int(radius + dy * scale)

    for raw_pos, marker_color in (
        (game.map_config.get("supplier_pos", game_client.SUPPLIER_POS), game_client.SUPPLIER_COLOR),
        (game.map_config.get("customer_pos", game_client.CUSTOMER_POS), game_client.CUSTOMER_COLOR),
    ):
        try:
            p = marker_point(raw_pos[0], raw_pos[1])
        except (TypeError, ValueError, IndexError, KeyError):
            p = None
        if p is not None:
            pygame.draw.circle(mini, (18, 24, 28), p, 7)
            pygame.draw.circle(mini, marker_color, p, 5)

    for pid, marker in game.map_players.items():
        if pid == game.local_id or not game.is_friend(str(marker.get("name", ""))):
            continue
        try:
            p = marker_point(marker.get("x", 0.0), marker.get("y", 0.0))
        except (TypeError, ValueError):
            p = None
        if p is not None:
            pygame.draw.circle(mini, (18, 24, 28), p, 6)
            pygame.draw.circle(mini, game_client.REMOTE_COLOR, p, 4)

    pygame.draw.circle(mini, tuple(ui.get("accent", game_client.LOCAL_COLOR)), (radius, radius), 5)
    heading = float(getattr(local, "aim", 0.0))
    tip = (int(radius + math.cos(heading) * 16), int(radius + math.sin(heading) * 16))
    left = (int(radius + math.cos(heading + 2.55) * 9), int(radius + math.sin(heading + 2.55) * 9))
    right = (int(radius + math.cos(heading - 2.55) * 9), int(radius + math.sin(heading - 2.55) * 9))
    pygame.draw.polygon(mini, (244, 244, 237), [tip, left, right])
    pygame.draw.polygon(mini, border, [tip, left, right], width=1)

    game.screen.blit(mini, (18, game.screen.get_height() - diameter - 58))
    north = game.small_font.render("N", True, game_client.TEXT_COLOR)
    game.screen.blit(north, (18 + radius - north.get_width() // 2, game.screen.get_height() - diameter - 53))

    # Until names have explicit GridWorld-owned anchors, identify the current
    # authoritative cell. No legacy landmark/district coordinates are read.
    cell_x, cell_y = world.world_to_cell(local.render_x, local.render_y)
    name = f"OPEN NIGHT — GRID {cell_x:02d},{cell_y:02d}"
    label_s = game.small_font.render(str(name).upper()[:28], True, game_client.TEXT_COLOR)
    box = pygame.Rect(18, game.screen.get_height() - 52, max(194, label_s.get_width() + 28), 38)
    pygame.draw.rect(game.screen, tuple(ui.get("panel", (28, 31, 31))), box, border_radius=3)
    pygame.draw.rect(game.screen, tuple(ui.get("panel_edge", (92, 92, 84))), box, width=1, border_radius=3)
    game.screen.blit(label_s, label_s.get_rect(center=box.center))


def _suppress_legacy_elevated_overlay(*_args, **_kwargs) -> None:
    """No retired bridge/upper-road overlay may bleed into v1.0 Ground."""
    return None


game_client.Game.draw_world = _draw_world_grid_exclusive
game_client.Game.draw_player = _draw_player_grid_scale
game_client.Game.draw_player_nameplates = _draw_nameplates_grid_scale
game_client.Game.draw_local_minimap = _draw_grid_local_minimap
game_client.Game._build_world_map_cache = _build_grid_world_map_cache
game_client.Game._draw_world_map_impl = _draw_grid_world_map_impl
game_client.EnvironmentRenderer.draw_elevated_overlay = _suppress_legacy_elevated_overlay


if __name__ == "__main__":
    asyncio.run(game_client.main())
