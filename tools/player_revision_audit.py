from __future__ import annotations

from pathlib import Path
import struct


ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "assets" / "characters" / "grunge_topdown"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def png_size(path: Path) -> tuple[int, int]:
    data = path.read_bytes()[:24]
    require(data[:8] == b"\x89PNG\r\n\x1a\n", f"not a PNG: {path}")
    return struct.unpack(">II", data[16:24])


def main() -> None:
    master = PACK / "master_8x10_v2_clean.png"
    require(master.is_file(), "clean v2.0 master character sheet is missing")
    require(png_size(master) == (1280, 1280), f"unexpected master dimensions: {png_size(master)}")

    hats = sorted((PACK / "hats").glob("hat_*.png"))
    heads = sorted((PACK / "heads").glob("head_*.png"))
    bodies = sorted((PACK / "bodies").glob("body_*.png"))
    require((len(hats), len(heads), len(bodies)) == (8, 8, 64), "replacement character layers are incomplete")
    require(all(png_size(path) == (160, 128) for path in hats + heads + bodies), "runtime layer size changed")

    canonical_client = (ROOT / "v100_client.py").read_text(encoding="utf-8")
    require("portrait_head_client" not in canonical_client, "retired portrait overlay still loads in the canonical client")
    runtime = (ROOT / "character_art.py").read_text(encoding="utf-8")
    require("def _composed_frame" in runtime and "pygame.transform.rotate" in runtime,
            "replacement layered renderer is incomplete")
    catalog = (ROOT / "character_catalog.py").read_text(encoding="utf-8")
    require('PART_SLOTS = ("hat", "head", "body")' in catalog, "v2.0 customization slots changed")

    client = (ROOT / "client.py").read_text(encoding="utf-8")
    for token in ('("Hat", "hat"', '("Head", "head"', '("Body", "body"'):
        require(token in client, f"launcher customization row missing: {token}")
    database = (ROOT / "database.py").read_text(encoding="utf-8")
    require('character_accessory VARCHAR(48)' in database, "compatible hat persistence field is missing")

    start = (ROOT / "START_OPEN_NIGHT.bat").read_text(encoding="utf-8")
    require("open_night_player_launcher.py" in start, "START_OPEN_NIGHT does not use player launcher")

    print("PLAYER_REVISION_GATE=PASS")
    print("character_pack=grunge_topdown")
    print("master_sheet=1280x1280")
    print("runtime_layers=80")


if __name__ == "__main__":
    main()
