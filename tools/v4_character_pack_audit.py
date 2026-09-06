"""Check every selectable v4 character part against the active art pack."""
from pathlib import Path
import sys
import json

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from character_catalog import pack_root, HATS, HEADS, BODIES, normalize_character
from PIL import Image


def main():
    active = pack_root()
    assert active == ROOT / "assets/characters/gunner_alpha_v1"
    manifest = json.loads((active / "manifest.json").read_text(encoding="utf-8"))
    paths = [active / "master_8x10_v2_clean.png"]
    paths += [active / "hats" / f"{part}.png" for part in HATS if part != "none"]
    paths += [active / "heads" / f"{part}.png" for part in HEADS]
    paths += [active / "bodies" / f"{part}_{state}.png"
              for part in BODIES for state in manifest["states"]]
    for path in paths:
        with Image.open(path) as sprite:
            sprite.load()
            assert sprite.mode == "RGBA", path
            assert sprite.getchannel("A").getbbox(), path
    for index in range(8):
        migrated = normalize_character({"top_color": index, "skin_tone": index})
        assert migrated["body"] in BODIES and migrated["head"] in HEADS
    print(f"V4 CHARACTER PACK: PASS ({len(paths)} active images; old account IDs supported)")
    print("Art manifest: retained hats; equipment references are not animation assets.")


if __name__ == "__main__":
    main()
