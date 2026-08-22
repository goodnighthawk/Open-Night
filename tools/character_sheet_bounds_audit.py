from __future__ import annotations

import struct
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "assets" / "characters" / "grunge_topdown"
CELL_SIZE = (160, 128)
STATES = ("idle", "walk_left", "walk_right", "run_left", "run_right", "jump", "crouch", "prone")


def _png_size(path: Path) -> tuple[int, int]:
    header = path.read_bytes()[:24]
    assert header[:8] == b"\x89PNG\r\n\x1a\n", f"not a PNG: {path}"
    assert header[12:16] == b"IHDR", f"missing PNG IHDR: {path}"
    return struct.unpack(">II", header[16:24])


def main() -> int:
    sys.path.insert(0, str(ROOT))
    import character_catalog

    assert character_catalog.pack_root().resolve() == PACK.resolve()
    expected = []
    for index in range(1, 9):
        expected.extend((PACK / "hats" / f"hat_{index:02d}.png", PACK / "heads" / f"head_{index:02d}.png"))
        expected.extend(PACK / "bodies" / f"body_{index:02d}_{state}.png" for state in STATES)
    assert len(expected) == 80
    for asset in expected:
        assert asset.is_file(), f"missing replacement sprite: {asset.relative_to(ROOT)}"
        assert _png_size(asset) == CELL_SIZE, f"wrong cell size: {asset.relative_to(ROOT)}"

    source = (ROOT / "character_art.py").read_text(encoding="utf-8")
    assert "master_dual_camera" not in source.replace("retired master_dual_camera", "")
    assert 'del mode  # Only the approved 90-degree pack exists.' in source
    assert "pygame.transform.rotate" in source

    print("CHARACTER SHEET BOUNDS AUDIT PASSED")
    print("  80 replacement layer assets / 160x128 cells / 90-degree renderer only")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
