from __future__ import annotations

"""Player-facing Open Night launcher.

Development-only viewers stay in the repository but are intentionally hidden
from the normal launcher until they are needed again.
"""

import sys

import open_night_launcher as base


class PlayerLauncher(base.OpenNightLauncher):
    def _layout_buttons(self):
        x, w = 840, 400
        specs = [
            ("01", "QUICK TEST", "memory server + protocol gate + client", self.launch_quick_test),
            ("02", "START SERVER", "authoritative server • portable .map + cache", self.launch_server),
            ("03", "DESKTOP CLIENT", "auto-detects Railway internet + LAN servers", self.launch_desktop),
        ]
        update = base.LaunchButton(
            self.pg,
            (828, 126, 424, 92),
            "UP",
            "UPDATE TO LATEST VERSION",
            "safe fast-forward update from GitHub main",
            self.launch_update,
            base.NEON_PINK,
        )
        actions = [
            base.LaunchButton(self.pg, (x, 250 + i * 84, w, 70), *spec)
            for i, spec in enumerate(specs)
        ]
        self.buttons = [update, *actions]

    def _draw_status(self, surf):
        pg = self.pg
        h = surf.get_height()
        box = pg.Rect(824, h - 61, 432, 43)
        pg.draw.rect(surf, (3, 8, 14), box, border_radius=6)
        accent = base.NEON_PINK if self.status_kind == "error" else base.NEON_BLUE
        pg.draw.rect(surf, accent, box, 1, border_radius=6)
        msg = self.fonts["status"].render(self.status, True, accent)
        surf.blit(msg, (box.x + 12, box.y + 7))
        online = f"SERVER {'ONLINE' if self.server_online else 'OFF'}"
        osurf = self.fonts["small"].render(online, True, base.NEON_WHITE)
        surf.blit(osurf, (box.x + 12, box.y + 24))


def main() -> int:
    try:
        import pygame
    except ImportError:
        print(
            "pygame-ce is required. Start with START_OPEN_NIGHT.bat so setup can install dependencies.",
            file=sys.stderr,
        )
        return 2
    pygame.init()
    try:
        return PlayerLauncher(pygame).run()
    finally:
        pygame.quit()


if __name__ == "__main__":
    raise SystemExit(main())
