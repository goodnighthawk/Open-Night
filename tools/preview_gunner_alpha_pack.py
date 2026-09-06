"""Validate and animate a staged gunner pack through the unchanged game renderer."""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import sys
import zipfile

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from PIL import Image
import pygame
import character_art as art

PACK = ROOT / "assets/characters/gunner_alpha_v1"
REVIEW = ROOT / "art_review/modular_gunner_2026-09-05"
STATES = tuple(art.MASTER_BODY_ROWS)
NAMES = ("Tactical", "Street", "Utility")


def appearance(body: int, head: int | None = None, hat: str = "none"):
    return {"profile": "custom", "body": f"body_{body:02d}",
            "head": f"head_{head or body:02d}", "hat": hat}


def main():
    pygame.init()
    pygame.display.set_mode((1, 1))
    master = Image.open(PACK/"master_8x10_v2_clean.png")
    assert master.size == (1280, 1280) and master.mode == "RGBA"
    expected = []
    for i in range(1, 9):
        expected += [(f"hats/hat_{i:02d}.png", 0, i-1), (f"heads/head_{i:02d}.png", 1, i-1)]
        expected += [(f"bodies/body_{i:02d}_{state}.png", row, i-1) for state, row in art.MASTER_BODY_ROWS.items()]
    for relative, row, column in expected:
        image = Image.open(PACK/relative)
        assert image.mode == "RGBA" and image.size == (160, 128), relative
        assert image.getchannel("A").getextrema() == (0, 255), relative
        assert image.tobytes() == master.crop((column*160, row*128, (column+1)*160, (row+1)*128)).tobytes(), relative
    # The override affects only this preview process, never the saved game.
    art.pack_root = lambda: PACK
    art.reload_character_style()
    font = pygame.font.Font(None, 20)
    small = pygame.font.Font(None, 16)
    contact = pygame.Surface((560, 8*132+44))
    contact.fill((39, 43, 47))
    for col, name in enumerate(NAMES):
        contact.blit(font.render(name, True, (244, 232, 213)), (144+col*138, 12))
    rendered = 0
    for row, state in enumerate(STATES):
        contact.blit(small.render(state, True, (217, 220, 224)), (8, row*132+95))
        for col in range(3):
            sprite = art.build_character_surface(appearance(col+1), animation=state,
                                                  aim_radians=-math.pi/2, scale=3)
            contact.blit(sprite, sprite.get_rect(center=(180+col*138, row*132+102)))

    # Exercise every persisted ID and hat option across all states and headings.
    # Rendering at these scales also catches empty rotated sprites and clipping.
    for body in range(1, 9):
        for head in range(1, 9):
            for state in STATES:
                composite = art._composed_frame("none", f"head_{head:02d}", f"body_{body:02d}", state)
                rect = composite.get_bounding_rect(min_alpha=16)
                assert rect.width > 12 and rect.height > 12
                assert rect.left > 0 and rect.top > 0 and rect.right < 224 and rect.bottom < 224
                for angle in (-math.pi/2, 0, math.pi/4, math.pi):
                    sprite = art.build_character_surface(appearance(body, head), animation=state, aim_radians=angle, scale=2)
                    assert pygame.mask.from_surface(sprite).count() > 100
                    rendered += 1
    for i in range(1, 9):
        for state in STATES:
            art.build_character_surface(appearance(i, hat=f"hat_{i:02d}"), animation=state, scale=2)
            rendered += 1

    REVIEW.mkdir(parents=True, exist_ok=True)
    pygame.image.save(contact, REVIEW/"alpha_movement_contact.png")
    mixes = pygame.Surface((450, 480))
    mixes.fill((39, 43, 47))
    for row in range(3):
        for col in range(3):
            sprite = art.build_character_surface(appearance(col+1, row+1), aim_radians=-math.pi/2, scale=3)
            mixes.blit(sprite, sprite.get_rect(center=(75+col*150, 78+row*160)))
            mixes.blit(small.render(f"Head {row+1} / {NAMES[col]}", True, (230, 230, 230)), (col*150+6, row*160+140))
    pygame.image.save(mixes, REVIEW/"alpha_head_outfit_combinations.png")

    frames = []
    timeline = [("walk", 40), ("run", 40), ("jump", 12), ("crouch", 12), ("prone", 18), ("idle", 12)]
    for state, length in timeline:
        for phase in range(length):
            canvas = pygame.Surface((600, 235))
            canvas.fill((39, 43, 47))
            canvas.blit(font.render(f"V4.0 renderer: {state}", True, (240, 236, 227)), (12, 12))
            for col, name in enumerate(NAMES):
                sprite = art.build_character_surface(appearance(col+1), animation=state, anim_time=phase/20,
                                                      aim_radians=-math.pi/2, scale=4)
                canvas.blit(sprite, sprite.get_rect(center=(100+col*200, 125)))
                canvas.blit(font.render(name, True, (230, 230, 230)), (60+col*200, 209))
            frames.append(Image.frombytes("RGB", canvas.get_size(), pygame.image.tobytes(canvas, "RGB")))
    frames[0].save(REVIEW/"alpha_movement_preview.gif", save_all=True, append_images=frames[1:], duration=50, loop=0)
    report = {"result": "pass", "layers_checked": len(expected), "render_cases": rendered,
              "unique_outfits": 3, "unique_heads": 3, "body_states": list(STATES),
              "master_matches_layers": True, "rgba_verified": True,
              "preview_uses_current_renderer": True, "live_pack_modified": False}
    (PACK/"validation.json").write_text(json.dumps(report, indent=2)+"\n", encoding="utf-8")
    with zipfile.ZipFile(REVIEW/"gunner_alpha_v1.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        for file in sorted(PACK.rglob("*")):
            if file.is_file():
                archive.write(file, "grunge_topdown/"+file.relative_to(PACK).as_posix())
    print(json.dumps(report))


if __name__ == "__main__":
    main()
