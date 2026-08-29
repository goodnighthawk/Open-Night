from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from common import blocked, move_with_collisions
from versioning import GAME_VERSION


def main() -> int:
    water_map = {
        "world_w": 500,
        "world_h": 500,
        "chunked": True,
        "water_polygons": [[[100, 100], [300, 100], [300, 300], [100, 300]]],
        "roads": [],
        "level_connectors": [],
        "buildings": [[340, 180, 50, 50]],
    }
    assert blocked(150, 150, water_map), "water must remain blocked by default"
    assert not blocked(150, 150, water_map, allow_water=True), "on-foot water opt-in failed"
    x, y = move_with_collisions(95, 150, 20, 0, water_map, allow_water=True)
    assert x == 115 and y == 150, "a pedestrian could not wade into water"
    assert blocked(355, 195, water_map, allow_water=True), "water opt-in must not bypass buildings"

    server = (ROOT / "server.py").read_text(encoding="utf-8")
    client = (ROOT / "client.py").read_text(encoding="utf-8")
    database = (ROOT / "database.py").read_text(encoding="utf-8")
    updater = (ROOT / "UPDATE_FRIEND_BUILD.bat").read_text(encoding="utf-8")
    assert f'GAME_VERSION = "{GAME_VERSION}"' in (ROOT / "versioning.py").read_text(encoding="utf-8")
    assert (ROOT / "VERSION.txt").read_text(encoding="utf-8-sig").strip() == GAME_VERSION
    for token in ("client_version", "Version mismatch", "required_version"):
        assert token in server or token in client, token
    for token in ("sms_messages", "create_sms_message", "load_sms_messages"):
        assert token in database, token
    for token in ("main.zip", "Expand-Archive", "robocopy", "friends.csv"):
        assert token in updater, token
    assert "allow_water=True" in server and "WATER_WALK_SPEED_MULTIPLIER" in server
    assert "_front_axle_rotated_center" in server and "runover_min_speed_mph" in server

    print(f"OPEN NIGHT v{GAME_VERSION} RELIABILITY AUDIT: PASS")
    print("  strict version gate + persistent SMS + water wading + friend updater contracts verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
