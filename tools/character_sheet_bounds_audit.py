from __future__ import annotations

import csv
import os
import struct
import sys
import tempfile
import types
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "assets" / "characters" / "master_dual_camera"


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _png_size(path: Path) -> tuple[int, int]:
    header = path.read_bytes()[:24]
    assert header[:8] == b"\x89PNG\r\n\x1a\n", f"not a PNG: {path}"
    assert header[12:16] == b"IHDR", f"missing PNG IHDR: {path}"
    return struct.unpack(">II", header[16:24])


def main() -> int:
    rows = _rows(PACK / "config" / "fluid_animations.csv")
    assert rows, "fluid animation registry is empty"
    checked_cells = 0
    for row in rows:
        sheet = PACK / row["sheet"]
        assert sheet.is_file(), f"missing sheet: {sheet.relative_to(ROOT)}"
        width, height = _png_size(sheet)
        cell_w = int(row.get("cell_width") or 256)
        cell_h = int(row.get("cell_height") or 256)
        frames = int(row.get("frame_count") or 1)
        directions = len([item for item in row.get("direction_rows", "").split(";") if item]) or 8
        assert width % cell_w == 0 and height % cell_h == 0, (
            f"partial grid cell in {sheet.relative_to(ROOT)}: {width}x{height} / {cell_w}x{cell_h}"
        )
        assert width // cell_w >= frames, (
            f"too few frames in {sheet.relative_to(ROOT)}: {width // cell_w} < {frames}"
        )
        assert height // cell_h >= directions, (
            f"too few directions in {sheet.relative_to(ROOT)}: {height // cell_h} < {directions}"
        )
        checked_cells += frames * directions

    # A normal release must select its matching bundled art instead of silently
    # inheriting an old Documents/PythonMMO_SharedData character pack.
    os.environ.pop("PYMMO_CHARACTER_PACK", None)
    sys.path.insert(0, str(ROOT))
    import character_catalog

    assert character_catalog.pack_root().resolve() == PACK.resolve()
    source = (ROOT / "character_art.py").read_text(encoding="utf-8")
    assert "def _safe_sheet_cell" in source
    assert "raw = _safe_sheet_cell(sheet, frame, direction)" in source

    # Exercise the exact crash boundary without requiring an initialized window:
    # wildly invalid runtime indices must be wrapped before Surface.subsurface.
    class FakeRect:
        def __init__(self, x: int, y: int, w: int, h: int):
            self.x, self.y, self.width, self.height = x, y, w, h

    class FakeSurface:
        def __init__(self, width: int, height: int):
            self.width, self.height = width, height
            self.last_rect: FakeRect | None = None

        def get_width(self) -> int:
            return self.width

        def get_height(self) -> int:
            return self.height

        def subsurface(self, rect: FakeRect) -> "FakeSurface":
            assert rect.x >= 0 and rect.y >= 0
            assert rect.x + rect.width <= self.width
            assert rect.y + rect.height <= self.height
            self.last_rect = rect
            return self

        def copy(self) -> "FakeSurface":
            return self

    fake_pygame = types.ModuleType("pygame")
    fake_pygame.Rect = FakeRect
    sys.modules["pygame"] = fake_pygame
    with tempfile.TemporaryDirectory(prefix="open_night_sheet_audit_") as shared_root:
        os.environ["PYMMO_SHARED_DATA"] = shared_root
        import character_art

        fake_sheet = FakeSurface(2 * character_art.CELL, character_art.CELL)
        assert character_art._safe_sheet_cell(fake_sheet, 999, 999) is fake_sheet
        assert fake_sheet.last_rect is not None
        assert fake_sheet.last_rect.x == character_art.CELL
        assert fake_sheet.last_rect.y == 0

    print("CHARACTER SHEET BOUNDS AUDIT PASSED")
    print(f"  {len(rows)} fluid sheets / {checked_cells} registered frame-direction cells")
    print("  bundled release pack selected / runtime crop guard exercised")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
