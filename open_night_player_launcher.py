from __future__ import annotations

"""Player-facing Open Night launcher.

Development-only viewers stay in the repository but are intentionally hidden
from the normal launcher until they are needed again.
"""

import sys

import open_night_launcher as base


class PlayerLauncher(base.OpenNightLauncher):
    def _layout_buttons(self):
        x, y, w, h, gap = 596, 126, 480, 78, 12
        specs = [
            ("01", "MAP GENERATOR", "semantic map + cosmetics + lighting", self.launch_map_generator),
            ("02", "QUICK TEST", "memory server + protocol gate + client", self.launch_quick_test),
            ("03", "START SERVER", "authoritative server • portable .map + cache", self.launch_server),
            ("04", "DESKTOP CLIENT", "auto-detects Railway internet + LAN servers", self.launch_desktop),
        ]
        self.buttons = [
            base.LaunchButton(self.pg, (x, y + i * (h + gap), w, h), *spec)
            for i, spec in enumerate(specs)
        ]

    def _draw_status(self, surf):
        pg = self.pg
        w, h = surf.get_size()
        box = pg.Rect(34, h - 66, w - 68, 40)
        pg.draw.rect(surf, base.PANEL, box)
        pg.draw.rect(surf, (68, 73, 58), box, 1)
        col = base.RED if self.status_kind == "error" else base.LIME
        msg = self.fonts["status"].render(self.status, True, col)
        surf.blit(msg, (box.x + 15, box.y + 11))
        online = f"SERVER {'ONLINE' if self.server_online else 'OFF'}"
        osurf = self.fonts["small"].render(online, True, base.CREAM)
        surf.blit(osurf, (box.right - osurf.get_width() - 14, box.y + 12))


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
