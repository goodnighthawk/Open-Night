"""Package generated RGBA layers into the existing v4.0 character contract.

This only slices, registers, and exports supplied art; it does not draw poses.
Keep the live pack unchanged. See manifest.json for the three-outfit ID aliases.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import shutil
import sys
import zipfile

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from PIL import Image
import numpy as np

OUT = ROOT / "assets/characters/gunner_alpha_v1"
REVIEW = ROOT / "art_review/modular_gunner_2026-09-05"
STATES = ("idle", "walk_left", "walk_right", "run_left", "run_right", "jump", "crouch", "prone")
VARIANTS = ("tactical", "street", "utility")
SHIFTS = dict(zip(STATES, (-24, -28, -34, -44, -44, -52, -58, -60)))
CELL = (160, 128)
HEAD_CENTER_Y = 90


def visible(image: Image.Image) -> tuple[int, int, int, int]:
    bounds = image.getchannel("A").point(lambda a: 255 if a > 16 else 0).getbbox()
    if bounds is None:
        raise ValueError("Empty sprite")
    return bounds


def neck_socket(image: Image.Image) -> tuple[float, float]:
    """Locate the dark neck opening near upper center, recording it for review."""
    a = np.asarray(image)
    h, w = a.shape[:2]
    dark = ((a[:, :, :3].max(axis=2) < 65) & (a[:, :, 3] > 32)).astype(float)
    # Neck holes are broad dark patches. Search only upper-middle torso, away
    # from hands and lower dark trousers. Integral windows avoid outline noise.
    r = max(3, round(w * .055))
    integral = np.pad(dark, ((1, 0), (1, 0))).cumsum(0).cumsum(1)
    best = None
    for y in range(max(r, int(h * .06)), min(h-r, int(h * .39))):
        for x in range(max(r, int(w * .30)), min(w-r, int(w * .70))):
            score = (integral[y+r+1, x+r+1] - integral[y-r, x+r+1]
                     - integral[y+r+1, x-r] + integral[y-r, x-r]) / (2*r+1)**2
            score -= .10 * abs(x/w - .5) + .06 * abs(y/h - .16)
            if best is None or score > best[0]:
                best = (score, x, y)
    if best is None:
        raise ValueError("Cannot locate neck socket")
    return float(best[1]), float(best[2])


def extract(path: Path):
    image = Image.open(path)
    if image.mode != "RGBA" or image.getchannel("A").getextrema()[0] != 0:
        raise ValueError(f"Requires actual RGBA transparency, got {image.mode}: {path}")
    items = []
    for index in range(9):
        col, row = index % 3, index // 3
        cell = image.crop((round(col*image.width/3), round(row*image.height/3),
                           round((col+1)*image.width/3), round((row+1)*image.height/3)))
        box = visible(cell)
        # Blank margins are necessary to avoid inadvertently including another
        # cell's artwork. Reject cut-off source silhouettes instead of clipping.
        if min(box[0], box[1], cell.width-box[2], cell.height-box[3]) < 2:
            raise ValueError(f"Source cell {index} touches boundary: {path}")
        items.append(cell.crop(box))
    return items


def pack_variant(path: Path):
    head, *bodies = extract(path)
    sockets = [neck_socket(body) for body in bodies]
    scales = []
    for state, body, (nx, ny) in zip(STATES, bodies, sockets):
        cy = HEAD_CENTER_Y + SHIFTS[state]
        scales.extend((62/(body.width/2), (cy-6)/max(ny, 1),
                       (122-cy)/max(body.height-ny, 1)))
    scale = min(scales)
    # A single geometric scale across the entire outfit preserves limb widths.
    layers = {}
    records = {}
    for state, body, (nx, ny) in zip(STATES, bodies, sockets):
        target = Image.new("RGBA", CELL)
        resized = body.resize((max(1, round(body.width*scale)), max(1, round(body.height*scale))), Image.Resampling.NEAREST)
        # The legacy renderer aligns heads to body BBOX center, not a socket x.
        # Center the neck opening by registering it first; the manifest records
        # remaining bbox asymmetry for the compatibility adapter/master export.
        x = round(80 - nx*scale)
        y = round(HEAD_CENTER_Y + SHIFTS[state] - ny*scale)
        if x < 0 or y < 0 or x+resized.width > 160 or y+resized.height > 128:
            raise ValueError(f"Registered layer clips: {state}")
        target.alpha_composite(resized, (x, y))
        layers[state] = target
        records[state] = {"source_neck": [nx, ny], "scale": scale,
                          "head_socket": [80, HEAD_CENTER_Y+SHIFTS[state]]}
    # Normalize head diameter across interchangeable identities, broad enough
    # to cover neck openings without changing the body pixels.
    head_scale = min(32/head.width, 35/head.height)
    head = head.resize((round(head.width*head_scale), round(head.height*head_scale)), Image.Resampling.NEAREST)
    head_layer = Image.new("RGBA", CELL)
    head_layer.alpha_composite(head, (80-head.width//2, HEAD_CENTER_Y-head.height//2))
    return head_layer, layers, records


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tactical", type=Path, required=True)
    parser.add_argument("--street", type=Path, required=True)
    parser.add_argument("--utility", type=Path, required=True)
    args = parser.parse_args()
    for folder in ("source", "heads", "hats", "bodies", "equipment_review"):
        (OUT/folder).mkdir(parents=True, exist_ok=True)
    data = {}
    registration = {}
    for variant in VARIANTS:
        src = getattr(args, variant).resolve()
        dest = OUT/"source"/f"{variant}_movement_rgba.png"
        if src != dest.resolve():
            shutil.copy2(src, dest)
        head, bodies, record = pack_variant(dest)
        data[variant] = (head, bodies)
        registration[variant] = record
        shutil.copy2(REVIEW/f"{variant}_equipment_v2.png", OUT/"equipment_review"/f"{variant}_equipment_concept.png")

    import pygame
    import character_art as art
    pygame.init()
    pygame.display.set_mode((1, 1))
    # Retain approved hats using precisely the existing runtime extraction.
    hats = []
    for i in range(1, 9):
        source = art._load_part(f"hats/hat_{i:02d}.png")
        raw = Image.frombytes("RGBA", source.get_size(), pygame.image.tobytes(source, "RGBA"))
        raw = raw.crop(visible(raw))
        ratio = min(36/raw.width, 39/raw.height)
        raw = raw.resize((round(raw.width*ratio), round(raw.height*ratio)), Image.Resampling.NEAREST)
        layer = Image.new("RGBA", CELL)
        layer.alpha_composite(raw, (80-raw.width//2, HEAD_CENTER_Y-raw.height//2))
        hats.append(layer)

    master = Image.new("RGBA", (1280, 1280))
    aliases = {}
    for index in range(1, 9):
        variant = VARIANTS[(index-1)%3]
        aliases[f"{index:02d}"] = variant
        head, bodies = data[variant]
        parts = [hats[index-1], head] + [bodies[s] for s in STATES]
        paths = [OUT/"hats"/f"hat_{index:02d}.png", OUT/"heads"/f"head_{index:02d}.png"]
        paths += [OUT/"bodies"/f"body_{index:02d}_{s}.png" for s in STATES]
        for row, (part, dest) in enumerate(zip(parts, paths)):
            part.save(dest)
            master.alpha_composite(part, ((index-1)*160, row*128))
    master.save(OUT/"master_8x10_v2_clean.png")
    manifest = {"schema": "open-night-grunge-topdown-compat-v1", "status": "alpha",
                "game_version": "4.0", "unique_outfits": list(VARIANTS),
                "unique_heads": 3, "retained_hats": 8, "compatibility_id_aliases": aliases,
                "cell_size": CELL, "master_size": [1280, 1280], "states": list(STATES),
                "head_center": [80, HEAD_CENTER_Y], "registration": registration,
                "equipment_status": "concept references only; current action renderer ignores weapon_id",
                "installed_as_default": False}
    (OUT/"manifest.json").write_text(json.dumps(manifest, indent=2)+"\n", encoding="utf-8")
    print(f"Built {OUT}: 80 RGBA layers + compatibility master")


if __name__ == "__main__":
    main()
