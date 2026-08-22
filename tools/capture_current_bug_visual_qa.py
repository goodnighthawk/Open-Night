from __future__ import annotations

import os
from pathlib import Path
import sys
import time

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pygame

import server
import v100_client
import v100_server
from common import traffic_light_states
from vehicle_art import draw_car

OUT = ROOT / "work" / "current_bug_visual_qa.png"
PANEL_W, PANEL_H = 640, 480


def main() -> None:
    pygame.init()
    pygame.display.set_mode((1, 1))
    v100_server.install_v100_server()
    server.TRAFFIC_COUNT = 28
    errors = v100_server.validate_active_authority(server.ACTIVE_MAP)
    if errors:
        raise RuntimeError(errors)

    game_client = v100_client.game_client
    game_client.NetworkClient.start = lambda self: None
    v100_client.install_v100_client()
    game = game_client.Game("ws://visual-qa.invalid:8765", "5550000199", "VisualQA")
    game.map_config = server.ACTIVE_MAP
    game.traffic_lights = traffic_light_states(server.ACTIVE_MAP, 1.0)
    world = game.grid_world
    renderer = game.grid_renderer
    if world is None or renderer is None:
        raise RuntimeError("GridWorld renderer unavailable")

    board = pygame.Surface((PANEL_W * 3, PANEL_H * 2)).convert()
    board.fill((9, 11, 15))
    title_font = pygame.font.Font(None, 28)
    label_font = pygame.font.Font(None, 22)

    def panel(index: int) -> pygame.Surface:
        return board.subsurface(pygame.Rect((index % 3) * PANEL_W, (index // 3) * PANEL_H, PANEL_W, PANEL_H))

    def caption(surface: pygame.Surface, title: str, detail: str) -> None:
        box = pygame.Surface((surface.get_width(), 58), pygame.SRCALPHA)
        box.fill((8, 10, 14, 220))
        surface.blit(box, (0, 0))
        surface.blit(title_font.render(title, True, (239, 240, 232)), (14, 8))
        surface.blit(label_font.render(detail, True, (151, 202, 235)), (14, 34))

    def render_at(surface: pygame.Surface, x: float, y: float) -> tuple[float, float]:
        camera = (
            max(0.0, min(world.world_w - surface.get_width(), x - surface.get_width() * 0.5)),
            max(0.0, min(world.world_h - surface.get_height(), y - surface.get_height() * 0.5)),
        )
        renderer.draw_view(surface, camera, "ground")
        return camera

    # Reported building/lamp area.
    p = panel(0)
    render_at(p, 5048.0, 1700.0)
    caption(p, "BUILDING + STREET LAMP", "perimeter frame removed • fixture head and blue pool over road")

    # Rounded curb and varied pavement.
    curb_cell = next(
        (gx, gy) for gy, row in enumerate(world.layers["ground"])
        for gx, tile in enumerate(row) if tile in {"curb_tl_outer", "curb_tr_outer", "curb_bl_outer", "curb_br_outer"}
    )
    curb_pos = world.cell_center(*curb_cell)
    p = panel(1)
    render_at(p, *curb_pos)
    caption(p, "CURB + PAVEMENT", "rounded source-pack corner • patterned/rotated pavement variants")

    # First working junction, including live synchronized fixtures.
    signal = server.ACTIVE_MAP["traffic_signals"][0]
    sx, sy = map(float, signal["pos"])
    p = panel(2)
    camera = render_at(p, sx, sy)
    old_screen, old_override = game.screen, game._render_camera_override
    game.screen = p
    game._render_camera_override = camera
    for fixture in server.ACTIVE_MAP["traffic_signals"]:
        fx, fy = map(float, fixture["pos"])
        if camera[0] - 80 <= fx <= camera[0] + PANEL_W + 80 and camera[1] - 80 <= fy <= camera[1] + PANEL_H + 80:
            game.draw_traffic_signal(fixture)
    game.screen, game._render_camera_override = old_screen, old_override
    caption(p, "WORKING JUNCTION SIGNALS", "four road-facing fixtures • synchronized red/green phases")

    # Exact reported vehicle art with the runtime forward light anchors.
    p = panel(3)
    p.fill((44, 49, 55))
    center = (PANEL_W // 2, PANEL_H // 2 + 20)
    if not draw_car(p, center, 0.0, 1, target_length=230, speed=0.0):
        raise RuntimeError("gridcar002 art unavailable")
    for side in (-1, 1):
        pygame.draw.circle(p, (255, 239, 173), (center[0] + 105, center[1] + side * 34), 8)
    pygame.draw.line(p, (80, 235, 130), (center[0] - 150, center[1] + 120), (center[0] + 150, center[1] + 120), 5)
    pygame.draw.polygon(p, (80, 235, 130), [(center[0] + 150, center[1] + 120), (center[0] + 130, center[1] + 108), (center[0] + 130, center[1] + 132)])
    caption(p, "GRIDCAR002 FORWARD CHECK", "sprite nose, headlights, indicators, and +X travel direction agree")

    # Functional Ground/roof endpoints at a fire escape.
    fire = next(item for item in world.objects if item.get("asset") == "placeholder_fire_escape")
    ground = world.cell_center(int(fire["gx"]), int(fire["gy"]))
    upward = world.fire_escape_transition(*ground, 0)
    if upward is None:
        raise RuntimeError("fire escape transition unavailable")
    roof = (upward[1], upward[2])
    p = panel(4)
    camera = render_at(p, (ground[0] + roof[0]) * 0.5, (ground[1] + roof[1]) * 0.5)
    points = [(int(ground[0] - camera[0]), int(ground[1] - camera[1])), (int(roof[0] - camera[0]), int(roof[1] - camera[1]))]
    pygame.draw.line(p, (245, 194, 77), points[0], points[1], 6)
    pygame.draw.circle(p, (85, 220, 125), points[0], 14, width=4)
    pygame.draw.circle(p, (89, 175, 246), points[1], 14, width=4)
    caption(p, "FUNCTIONAL FIRE ESCAPE", "stationary SPACE: Ground -> roof • SPACE again: roof -> Ground")

    # Main gameplay HUD with the always-visible controls.
    p = panel(5)
    spawn_x, spawn_y = world.login_spawns[0]
    render_at(p, spawn_x, spawn_y)
    local = game_client.RemotePlayer({
        "id": "qa-local", "name": "VisualQA", "x": spawn_x, "y": spawn_y,
        "aim": 0.0, "cash": 420, "packages": 2, "level": 0, "appearance": None,
    })
    game.local_id = local.id
    game.players = {local.id: local}
    game.map_players = {local.id: {"id": local.id, "name": local.name, "x": spawn_x, "y": spawn_y, "level": 0}}
    old_screen = game.screen
    game.screen = p
    game.connected = True
    game.notice = "Visible music + game-audio controls"
    game.notice_until = time.monotonic() + 60.0
    game.draw_hud()
    game.screen = old_screen
    caption(p, "MAIN GAMEPLAY AUDIO CONTROLS", "large music mute + smaller game-audio mute remain clickable on HUD")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    pygame.image.save(board, OUT)
    print(OUT)


if __name__ == "__main__":
    main()
