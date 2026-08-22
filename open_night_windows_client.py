from __future__ import annotations

"""Windows/Nuitka entry point for the player-facing Open Night client."""

import asyncio
import ctypes
import os
import tempfile
import traceback
from pathlib import Path


APP_TITLE = "Open Night"
PUBLISHER = "Snakepit LLC"


def _runtime_log_dir() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
    base = Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local"
    path = base / PUBLISHER / APP_TITLE / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _close_nuitka_splash() -> None:
    """Tell Nuitka's one-file bootstrap that the client is ready to draw."""

    parent_pid = os.environ.get("NUITKA_ONEFILE_PARENT", "").strip()
    if not parent_pid:
        return
    try:
        feedback = Path(tempfile.gettempdir()) / f"onefile_{int(parent_pid)}_splash_feedback.tmp"
        feedback.unlink(missing_ok=True)
    except (OSError, ValueError):
        # The bootstrap also removes the splash when the child exits, so a
        # missing feedback file is safe and must never prevent the game launch.
        pass


def _show_fatal_error(log_path: Path) -> None:
    message = (
        "Open Night could not start.\n\n"
        f"A diagnostic report was saved to:\n{log_path}"
    )
    try:
        ctypes.windll.user32.MessageBoxW(None, message, APP_TITLE, 0x10)
    except (AttributeError, OSError):
        pass


def _run_package_smoke_test() -> int:
    """Validate imports and embedded data without opening the game window."""

    import imageio_ffmpeg
    import pygame

    from portable_paths import APP_DIR

    expected = (
        APP_DIR / "VERSION.txt",
        APP_DIR / "config" / "public_servers.csv",
        APP_DIR / "mapfiles" / "data" / "map_001_gwb_corridor" / "grid_v100" / "ground_grid.json",
        APP_DIR / "assets" / "branding" / "snakepit_splash.png",
        APP_DIR / "assets" / "characters" / "grunge_topdown",
        APP_DIR / "assets" / "source_packs" / "SFX",
    )
    missing = [str(path) for path in expected if not path.exists()]
    ffmpeg_path = Path(imageio_ffmpeg.get_ffmpeg_exe())
    if not ffmpeg_path.is_file():
        missing.append(str(ffmpeg_path))

    report = [
        "Open Night packaged-client smoke test",
        f"pygame={pygame.version.ver}",
        f"runtime_root={APP_DIR}",
        f"ffmpeg={ffmpeg_path}",
        f"result={'PASS' if not missing else 'FAIL'}",
    ]
    if missing:
        report.extend(f"missing={path}" for path in missing)

    report_path_raw = os.environ.get("OPEN_NIGHT_SMOKE_REPORT", "").strip()
    report_path = Path(report_path_raw) if report_path_raw else _runtime_log_dir() / "package-smoke-test.txt"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(report) + "\n", encoding="utf-8")
    _close_nuitka_splash()
    return 0 if not missing else 3


async def _run_game() -> None:
    import v100_client

    # Complete the release patches while the branded splash remains visible.
    v100_client.install_v100_client()
    _close_nuitka_splash()
    await v100_client.game_client.main()


def main() -> int:
    if os.environ.get("OPEN_NIGHT_PACKAGE_SMOKE_TEST") == "1":
        return _run_package_smoke_test()

    try:
        asyncio.run(_run_game())
        return 0
    except BaseException:
        _close_nuitka_splash()
        log_path = _runtime_log_dir() / "client-crash.log"
        log_path.write_text(traceback.format_exc(), encoding="utf-8")
        _show_fatal_error(log_path)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
