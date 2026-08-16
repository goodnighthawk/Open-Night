from __future__ import annotations

import ast
import base64
import pathlib
import struct
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from portrait_head_asset import HEAD_ATLAS_B64, HEAD_RECTS


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def main() -> None:
    require(len(HEAD_RECTS) == 17, f"expected 17 selectable heads, got {len(HEAD_RECTS)}")
    png = base64.b64decode(HEAD_ATLAS_B64, validate=True)
    require(png.startswith(b"\x89PNG\r\n\x1a\n"), "embedded head atlas is not a PNG")
    width, height = struct.unpack(">II", png[16:24])
    require((width, height) == (140, 112), f"unexpected atlas dimensions {(width, height)}")
    for index, (x, y, w, h) in enumerate(HEAD_RECTS):
        require(w > 0 and h > 0 and x >= 0 and y >= 0, f"invalid head rect {index}")
        require(x + w <= width and y + h <= height, f"head rect {index} outside atlas")
        skin_tone, hair_style = divmod(index, 5)
        require(skin_tone * 5 + hair_style == index, f"head encoding failed for {index}")
        require(0 <= skin_tone < 5 and 0 <= hair_style < 5, f"head encoding exceeds server limits for {index}")

    for filename in ("portrait_head_asset.py", "portrait_head_client.py", "open_night_player_launcher.py"):
        ast.parse((ROOT / filename).read_text(encoding="utf-8"), filename=filename)

    run_client = (ROOT / "RUN_CLIENT.bat").read_text(encoding="utf-8")
    require("portrait_head_client.py" in run_client, "desktop launcher does not use head-selector client")
    start = (ROOT / "START_OPEN_NIGHT.bat").read_text(encoding="utf-8")
    require("open_night_player_launcher.py" in start, "START_OPEN_NIGHT does not use player launcher")

    player_launcher = (ROOT / "open_night_player_launcher.py").read_text(encoding="utf-8")
    for hidden in ("WEB CLIENT", "MOVEMENT PREVIEW", "MAP VIEWER"):
        require(hidden not in player_launcher, f"{hidden} still exposed in player launcher")
    for visible in ("MAP GENERATOR", "QUICK TEST", "START SERVER", "DESKTOP CLIENT"):
        require(visible in player_launcher, f"{visible} missing from player launcher")

    character_catalog = (ROOT / "character_catalog.py").read_text(encoding="utf-8")
    require('"skin_tone": 5' in character_catalog, "skin_tone server limit changed")
    require('"hair_style": 5' in character_catalog, "hair_style server limit changed")
    require('"top_color": 8' in character_catalog, "portrait sentinel no longer fits top_color")

    print("PLAYER_REVISION_GATE=PASS")
    print("selectable_heads=17")
    print("atlas=140x112")
    print("launcher_buttons=4")


if __name__ == "__main__":
    main()
