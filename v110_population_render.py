from __future__ import annotations

"""Keep v1.1 ambient-character proportions synchronized with the player.

Persistent shared settings can predate the v1.1 profile.  In particular, some
installations retained player_scale=2 while npc_scale remained 1, making every
pedestrian and dog look half-sized next to the local player.  Treat the player's
chosen/readable scale as the minimum scale for ambient characters instead of
silently trusting a stale NPC-only setting.
"""

import math
import time


MAX_AMBIENT_SCALE = 3.0


def _setting_scale(settings: dict, key: str, default: float = 1.0) -> float:
    try:
        value = float((settings.get("render", {}) or {}).get(key, default))
    except (TypeError, ValueError):
        value = float(default)
    return max(0.5, min(MAX_AMBIENT_SCALE, value))


def effective_npc_scale(settings: dict) -> float:
    return max(_setting_scale(settings, "player_scale"), _setting_scale(settings, "npc_scale"))


def effective_dog_scale(settings: dict) -> float:
    # The source dog sprite is naturally shorter than a human, so applying the
    # same multiplicative scale preserves that relationship while preventing a
    # stale 1x dog from sitting beside a 2x player.
    return max(1.0, _setting_scale(settings, "player_scale"))


def install(game_client) -> None:
    game = game_client.Game
    if bool(getattr(game, "_v110_population_render_installed", False)):
        return

    def draw_npc_v110(self, npc) -> None:
        sx, sy = self.world_to_screen(npc.render_x, npc.render_y)
        moving = time.monotonic() < npc.moving_until
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
                effective_dog_scale(self.settings),
            )
            self.screen.blit(rotated, rotated.get_rect(center=(sx, sy)))
            return

        game_client.draw_character(
            self.screen,
            (sx, sy),
            npc.aim,
            npc.appearance,
            scale=effective_npc_scale(self.settings),
            moving=moving,
            anim_time=time.monotonic() - npc.anim_epoch,
        )

    game.draw_npc = draw_npc_v110
    game._v110_population_render_installed = True
