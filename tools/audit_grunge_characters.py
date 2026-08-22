"""Verify the replacement character pack and render a movement contact sheet."""

from __future__ import annotations

import os
from pathlib import Path
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pygame

from character_art import build_character_surface
from character_catalog import custom_options, normalize_character, preset_options


def main() -> None:
    pygame.init()
    pygame.display.set_mode((1, 1))
    pack = ROOT / "assets" / "characters" / "grunge_topdown"
    assert len(list((pack / "hats").glob("hat_*.png"))) == 8
    assert len(list((pack / "heads").glob("head_*.png"))) == 8
    assert len(list((pack / "bodies").glob("body_*.png"))) == 64
    assert [len(custom_options()[key]) for key in ("hat", "head", "body")] == [9, 8, 8]
    assert len(preset_options()) == 8

    migrated = normalize_character({"hair_style": 4, "skin_tone": 3, "top_color": 6})
    assert migrated["hat"] == "hat_05" and migrated["head"] == "head_04" and migrated["body"] == "body_07"
    custom = normalize_character({"profile": "custom", "hat": "none", "head": "head_08", "body": "body_02"})
    assert (custom["hat"], custom["head"], custom["body"]) == ("none", "head_08", "body_02")
    persisted = normalize_character({
        "profile": "custom", "accessory": "hat_06", "head": "head_03", "body": "body_07",
    })
    assert (persisted["hat"], persisted["accessory"], persisted["head"], persisted["body"]) == (
        "hat_06", "hat_06", "head_03", "body_07",
    )

    states = ("idle", "walk_left", "walk_right", "run_left", "run_right", "jump", "crouch", "prone")
    sheet = pygame.Surface((8 * 112, 8 * 112), pygame.SRCALPHA)
    sheet.fill((42, 45, 49, 255))
    font = pygame.font.Font(None, 17)
    for row, state in enumerate(states):
        for col in range(8):
            appearance = {"hat": f"hat_{col + 1:02d}", "head": f"head_{col + 1:02d}", "body": f"body_{col + 1:02d}"}
            sprite = build_character_surface(appearance, aim_radians=-1.57079632679, scale=3, animation=state)
            cell = pygame.Rect(col * 112, row * 112, 112, 112)
            sheet.blit(sprite, sprite.get_rect(center=(cell.centerx, cell.centery + 4)))
            if col == 0:
                sheet.blit(font.render(state, True, (235, 235, 225)), (cell.x + 4, cell.y + 4))
    output = ROOT / "work" / "grunge_character_movement_preview.png"
    output.parent.mkdir(parents=True, exist_ok=True)
    pygame.image.save(sheet, output)
    print(f"PASS: 8 hats, 8 heads, 8 bodies x 8 movement states; preview={output}")


if __name__ == "__main__":
    main()
