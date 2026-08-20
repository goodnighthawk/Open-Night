from __future__ import annotations

"""Keep v1.1 ambient-character proportions synchronized with the player.

GridWorld Ground deliberately renders players at a minimum 2x legacy character
scale to match the normalized 128 px streets.  The original NPC renderer did not
share that temporary Ground-scale contract, so pedestrians and dogs remained 1x.
Persistent shared settings can amplify the mismatch.  This module gives ambient
characters the same minimum Ground scale while still respecting larger user/NPC
render settings.
"""

import math
import time


GRID_GROUND_MIN_SCALE = 2.0
MAX_AMBIENT_SCALE = 3.0


def _setting_scale(settings: dict, key: str, default: float = 1.0) -> float:
    try:
        value = float((settings.get("render", {}) or {}).get(key, default))
    except (TypeError, ValueError):
        value = float(default)
    return max(0.5, min(MAX_AMBIENT_SCALE, value))


def effective_npc_scale(settings: dict, *, grid_ground: bool = False) -> float:
    minimum = GRID_GROUND_MIN_SCALE if grid_ground else 0.5
    return max(minimum, _setting_scale(settings, "player_scale"), _setting_scale(settings, "npc_scale"))


def effective_dog_scale(settings: dict, *, grid_ground: bool = False) -> float:
    # The source dog sprite is naturally shorter than a human. Applying the same
    # multiplicative Ground scale preserves that relationship without leaving a
    # 1x dog beside a 2x GridWorld player.
    minimum = GRID_GROUND_MIN_SCALE if grid_ground else 1.0
    return max(minimum, _setting_scale(settings, "player_scale"))


def _grid_ground_active(game) -> bool:
    if getattr(game, "grid_world", None) is None or getattr(game, "grid_renderer", None) is None:
        return False
    local = game.players.get(game.local_id or "")
    level = int(getattr(local, "level", 0)) if local is not None else 0
    return level == 0


def install(game_client) -> None:
    game = game_client.Game
    if bool(getattr(game, "_v110_population_render_installed", False)):
        return

    def draw_npc_v110(self, npc) -> None:
        sx, sy = self.world_to_screen(npc.render_x, npc.render_y)
        moving = time.monotonic() < npc.moving_until
        grid_ground = _grid_ground_active(self)
        if getattr(npc, "kind", "pedestrian") == "dog":
            sprite = game_client.pygame.Surface((34, 22), game_client.pygame.SRCALPHA)
            game_client.pygame.draw.ellipse(sprite, (91, 68, 48), game_client.pygame.Rect(7, 6, 21, 11))
            game_client.pygame.draw.circle(sprite, (104, 78, 54), (28, 10), 6)
            game_client.pygame.draw.polygon(sprite, (70, 49, 34), [(27, 5), (29, 1), (31, 6)])
            game_client.pygame.draw.line(sprite, (70, 49, 34), (7, 10), (2, 5), 3)
            gait = 2 if moving and int((time.monotonic() - npc.anim_epoch) * 8) % 2 else 0
            for lx in (10, 22):
                game_client.pygame.draw.line(sprite, (65, 47, 34), (lx, 15), (lx - gait, 20), 2)
            rotated = game_client.pygame.transform.rotozoom(
                sprite,
                -math.degrees(npc.aim),
                effective_dog_scale(self.settings, grid_ground=grid_ground),
            )
            self.screen.blit(rotated, rotated.get_rect(center=(sx, sy)))
            return

        game_client.draw_character(
            self.screen,
            (sx, sy),
            npc.aim,
            npc.appearance,
            scale=effective_npc_scale(self.settings, grid_ground=grid_ground),
            moving=moving,
            anim_time=time.monotonic() - npc.anim_epoch,
        )

    game.draw_npc = draw_npc_v110
    game._v110_population_render_installed = True
