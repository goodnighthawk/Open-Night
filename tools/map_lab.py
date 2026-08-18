#!/usr/bin/env python3
"""Open Night Map Lab: local hot-reload visual iteration loop."""
from __future__ import annotations

import functools
import http.server
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_ROOT = ROOT / "artifacts" / "map_lab"
RENDER_SCRIPT = ROOT / "tools" / "map_lab_render.py"

WATCH_FILES = (
    ROOT / "grid_world.py",
    ROOT / "grid_renderer.py",
    ROOT / "grid_runtime.py",
    ROOT / "tools" / "generate_v100_ground_roof_layers.py",
    ROOT / "tools" / "map_lab_render.py",
    ROOT / "mapfiles" / "data" / "map_001_gwb_corridor" / "grid_v100" / "ground_grid.json",
    ROOT / "assets" / "grid_v100" / "tile_catalog.json",
    ROOT / "assets" / "grid_v100" / "building_tiles.json",
    ROOT / "assets" / "grid_v100" / "curb_orientation.json",
)
WATCH_DIRS = (
    ROOT / "assets" / "source_packs" / "city_block",
)
WATCH_SUFFIXES = {".py", ".json", ".png", ".ppm", ".svg"}


def _watched_paths() -> list[Path]:
    paths = [path for path in WATCH_FILES if path.is_file()]
    for directory in WATCH_DIRS:
        if not directory.is_dir():
            continue
        paths.extend(
            path for path in directory.rglob("*")
            if path.is_file() and path.suffix.lower() in WATCH_SUFFIXES
        )
    return sorted(set(paths))


def _fingerprint() -> tuple[tuple[str, int, int], ...]:
    rows = []
    for path in _watched_paths():
        try:
            stat = path.stat()
        except FileNotFoundError:
            continue
        rows.append((str(path.relative_to(ROOT)), stat.st_mtime_ns, stat.st_size))
    return tuple(rows)


def _render() -> bool:
    print("\n[Map Lab] Regenerating Ground + Roof proofs...")
    result = subprocess.run([sys.executable, str(RENDER_SCRIPT)], cwd=str(ROOT))
    if result.returncode:
        print("[Map Lab] Render failed. Fix the error above; the previous successful gallery is preserved.")
        return False
    return True


def _free_port(start: int = 8765) -> int:
    for port in range(start, start + 25):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    raise RuntimeError("Could not find a free local Map Lab port")


def _start_server() -> tuple[http.server.ThreadingHTTPServer, int]:
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(OUT_ROOT))
    port = _free_port()
    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, port


def main() -> None:
    if not RENDER_SCRIPT.is_file():
        raise SystemExit(f"Missing {RENDER_SCRIPT}")

    if not _render():
        raise SystemExit(1)

    server, port = _start_server()
    url = f"http://127.0.0.1:{port}/current/index.html"
    print(f"[Map Lab] Gallery: {url}")
    print("[Map Lab] WATCH ON — save a map, runtime, generator, catalog, or city_block asset to rerender.")
    print("[Map Lab] GitHub Actions are not involved. Press Ctrl+C here to stop.")
    webbrowser.open(url)

    last = _fingerprint()
    try:
        while True:
            time.sleep(0.8)
            current = _fingerprint()
            if current == last:
                continue
            print("[Map Lab] Change detected. Waiting briefly for the save to finish...")
            time.sleep(0.35)
            if _render():
                print("[Map Lab] Updated. Browser gallery auto-refreshes every 2 seconds.")
            last = _fingerprint()
    except KeyboardInterrupt:
        print("\n[Map Lab] Stopped.")
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()
