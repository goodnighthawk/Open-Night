from __future__ import annotations

import math
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from client import RemoteVehicle
from common import SERVER_TICK_RATE
from server import MOVEMENT_STREAM_RATE


def make_vehicle() -> RemoteVehicle:
    return RemoteVehicle({
        "id": "authority-audit-car",
        "x": 100.0,
        "y": 200.0,
        "angle": math.radians(20.0),
        "speed": 0.0,
        "driver": "player",
    })


def simulate_render_rate(fps: int) -> tuple[float, float, float]:
    vehicle = make_vehicle()
    vehicle.update({
        "x": 220.0,
        "y": 260.0,
        "angle": math.radians(40.0),
        "speed": 180.0,
    })
    for _ in range(fps):
        vehicle.smooth(1.0 / fps)
    return vehicle.render_x, vehicle.render_y, vehicle.angle


def main() -> int:
    assert SERVER_TICK_RATE == 60
    assert math.isclose(MOVEMENT_STREAM_RATE, 60.0)

    vehicle = make_vehicle()
    initial_render = (vehicle.render_x, vehicle.render_y, vehicle.angle)
    vehicle.update({
        "x": 220.0,
        "y": 260.0,
        "angle": math.radians(40.0),
        "speed": 180.0,
    })

    # Network updates only move authoritative targets. The client does not
    # predict or directly simulate a player-controlled road vehicle.
    assert (vehicle.render_x, vehicle.render_y, vehicle.angle) == initial_render
    assert (vehicle.target_x, vehicle.target_y) == (220.0, 260.0)
    assert math.isclose(vehicle.target_angle, math.radians(40.0))

    vehicle.smooth(1.0 / 60.0)
    assert 100.0 < vehicle.render_x < vehicle.target_x
    assert 200.0 < vehicle.render_y < vehicle.target_y
    assert vehicle.angle > initial_render[2]

    # Exponential smoothing should produce the same one-second result at
    # different render rates while consuming the same 60 Hz server targets.
    at_60 = simulate_render_rate(60)
    at_120 = simulate_render_rate(120)
    for value_60, value_120 in zip(at_60, at_120):
        assert math.isclose(value_60, value_120, rel_tol=1e-9, abs_tol=1e-9)

    print("V4 VEHICLE AUTHORITY AUDIT: PASS")
    print("  60 Hz server authority + target-only updates + frame-rate-independent smoothing verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
