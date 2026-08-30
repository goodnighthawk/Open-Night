from __future__ import annotations

import argparse
import asyncio
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from portable_paths import ensure_shared_layout
from stress_test_bots import load_settings, run_stage
from websockets.asyncio.client import connect


def available_local_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


async def wait_for_server(port: int, process: subprocess.Popen, timeout: float = 20.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"local proof server exited with code {process.returncode}")
        try:
            async with connect(f"ws://127.0.0.1:{port}", open_timeout=1.0):
                return
        except OSError:
            await asyncio.sleep(0.1)
            continue
        except Exception:
            await asyncio.sleep(0.1)
    raise TimeoutError("local proof server did not open its WebSocket port")


async def run_proof(duration: float) -> int:
    port = available_local_port()
    shared = ensure_shared_layout()
    stamp = time.strftime("%Y%m%d_%H%M%S")
    server_log = shared["stress_results"] / f"v4_city_server_{stamp}.log"
    command = [
        sys.executable,
        "-u",
        str(ROOT / "server.py"),
        "--host", "127.0.0.1",
        "--port", str(port),
        "--name", "Open Night v4 City Load Proof",
        "--max-players", "64",
        "--memory-db",
        "--no-discovery",
    ]
    environment = os.environ.copy()
    environment["PYTHONUNBUFFERED"] = "1"

    print(f"Starting isolated 64-player server on ws://127.0.0.1:{port}")
    with server_log.open("w", encoding="utf-8") as log_handle:
        process = subprocess.Popen(
            command,
            cwd=ROOT,
            env=environment,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            text=True,
        )
        try:
            await wait_for_server(port, process)
            cfg = load_settings()
            cfg["server_uri"] = f"ws://127.0.0.1:{port}"
            result = await run_stage(cfg, 64, max(1.0, duration))
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    await asyncio.to_thread(process.wait, 5.0)
                except subprocess.TimeoutExpired:
                    process.kill()
                    await asyncio.to_thread(process.wait, 5.0)

    print(f"Server log: {server_log}")
    return 0 if result["v4_city_proof"] == "PASS" else 1


def main() -> int:
    cfg = load_settings()
    parser = argparse.ArgumentParser(
        description="Run the isolated Open Night v4 64-player city-wide load proof"
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=float(cfg.get("duration_seconds", 60)),
        help="Seconds all 64 bots remain connected after the login ramp",
    )
    args = parser.parse_args()
    return asyncio.run(run_proof(max(1.0, args.duration)))


if __name__ == "__main__":
    raise SystemExit(main())
