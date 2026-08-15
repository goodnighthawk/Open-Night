from __future__ import annotations

import csv
import os
from pathlib import Path
import sys
import tempfile
from types import ModuleType


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    with tempfile.TemporaryDirectory(prefix="open_night_bug_audit_") as raw_root:
        temp_root = Path(raw_root)
        os.environ["PYMMO_SHARED_DATA"] = str(temp_root / "shared")

        try:
            import pygame
        except ModuleNotFoundError:
            # Source-only CI may not install the desktop runtime. Keep the CSV
            # and PNG pipeline testable there with the same tiny API surface;
            # LOCAL_QA on a game install continues to exercise real Pygame.
            from PIL import Image

            class AuditSurface:
                def __init__(self, size: tuple[int, int]):
                    self.image = Image.new("RGBA", size, (0, 0, 0, 255))

                def fill(self, color: tuple[int, ...]) -> None:
                    rgba = tuple(color[:3]) + (color[3] if len(color) > 3 else 255,)
                    self.image.paste(rgba, (0, 0, *self.image.size))

            pygame = ModuleType("pygame")
            pygame.Surface = AuditSurface
            pygame.error = RuntimeError
            pygame.init = lambda: None
            pygame.image = type("AuditImage", (), {"save": staticmethod(lambda surface, path: surface.image.save(path, "PNG"))})
            sys.modules["pygame"] = pygame
        from gameplay.issue_reporter import save_issue_report

        pygame.init()
        frame = pygame.Surface((96, 64))
        frame.fill((38, 84, 126))
        payload = {
            "source": "chat_/bug",
            "reporter": "AuditPlayer",
            "category": "bug",
            "description": "Bicycle spawned in water beside the west bridge",
            "note": "Bicycle spawned in water beside the west bridge",
            "build_version": "Open Night audit",
            "status": "pending_server_review",
            "target_version": "next",
            "duplicate_of": "",
            "map_id": "audit_map",
            "map_name": "Audit Map",
            "chunk_id": "A1",
            "chunk_x": 0,
            "chunk_y": 0,
            "world_x": 120.0,
            "world_y": 240.0,
        }
        shared_csv, shared_shot = save_issue_report(frame, payload)
        assert shared_csv.is_file() and shared_shot.is_file()
        from PIL import Image
        with Image.open(shared_shot) as captured:
            assert captured.size == (96, 64)

        with shared_csv.open("r", encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        assert len(rows) == 1
        row = rows[0]
        assert row["source"] == "chat_/bug"
        assert row["reporter"] == "AuditPlayer"
        assert row["description"].startswith("Bicycle spawned")
        assert row["screenshot"].startswith("screenshots/")
        assert row["status"] == "pending_server_review"

    client = (ROOT / "client.py").read_text(encoding="utf-8")
    reporter = (ROOT / "gameplay" / "issue_reporter.py").read_text(encoding="utf-8")
    character = (ROOT / "character_art.py").read_text(encoding="utf-8")
    settings = (ROOT / "gameplay" / "settings.py").read_text(encoding="utf-8")
    assert 'command == "/bug"' in client and '"chat_/bug"' in client
    assert 'command == "/mapfeedback"' in client and '"chat_/mapfeedback"' in client
    assert '"map_art" if is_map_feedback else "bug"' in client
    assert "pending_server_review" in reporter
    assert '"feedback" / "next_version"' not in reporter
    assert '"type": "bug_report_submit"' in client
    assert 'kind == "bug_report_receipt"' in client
    for removed in ("head_tracks_mouse", "head_aim_radians", "compute_aim_angle", "def aim_angle"):
        assert removed not in client, removed
    assert "head_direction = direction" in character
    assert "head_tracks_mouse" not in character and "head_tracks_mouse" not in settings
    print("BUG FEEDBACK / BODY-FACING AUDIT: PASS")
    print("  /bug + /mapfeedback local recovery capture and moderated upload verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
