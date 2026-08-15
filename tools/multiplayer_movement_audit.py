from __future__ import annotations

import math
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
os.environ.setdefault("PYMMO_SHARED_DATA", tempfile.mkdtemp(prefix="open_night_movement_audit_"))

from common import PlayerState
from server import (
    ClientSession,
    DOUBLE_JUMP_DURATION_SECONDS,
    DOUBLE_JUMP_FORWARD_SPEED,
    JUMP_DURATION_SECONDS,
    JUMP_FORWARD_SPEED,
    finish_expired_player_jump,
    request_player_jump,
    request_player_prone_toggle,
)

def main() -> int:
    session = ClientSession(
        websocket=None,  # type: ignore[arg-type]
        player=PlayerState("movement-audit", "Movement Audit", 100.0, 100.0),
        phone="audit",
        inventory=[],
        input_x=1.0,
        input_y=0.0,
        aim=0.0,
    )

    assert request_player_jump(session, 100.0) == "jump"
    assert session.jump_kind == "jump"
    assert math.isclose(session.jump_until, 100.0 + JUMP_DURATION_SECONDS)
    assert math.isclose(math.hypot(session.jump_velocity_x, session.jump_velocity_y), JUMP_FORWARD_SPEED)

    assert request_player_jump(session, 100.2) == "double_jump"
    assert session.jump_kind == "double_jump"
    assert math.isclose(session.jump_until, 100.2 + DOUBLE_JUMP_DURATION_SECONDS)
    assert math.isclose(math.hypot(session.jump_velocity_x, session.jump_velocity_y), DOUBLE_JUMP_FORWARD_SPEED)
    assert finish_expired_player_jump(session, session.jump_until + 0.01) == "double_jump"
    assert session.prone

    assert request_player_jump(session, 200.0) == "stand"
    assert not session.prone and not session.jump_kind
    assert request_player_prone_toggle(session, 201.0)
    assert session.prone
    assert request_player_prone_toggle(session, 202.0)
    assert not session.prone

    client_source = (ROOT / "client.py").read_text(encoding="utf-8")
    server_source = (ROOT / "server.py").read_text(encoding="utf-8")
    tester_source = (ROOT / "dev_tools/character_preview/sprite_tester.py").read_text(encoding="utf-8")
    assert "register_direction_tap" not in client_source
    assert "sprint_trigger_key" not in client_source
    assert "and shift_boost" in client_source
    assert '"prone_toggle"' in client_source
    assert 'other.jump_kind in {"jump", "double_jump"}' in server_source
    assert 'MOVEMENT_SETTINGS.get("walk_speed_px_per_second", PLAYER_SPEED)' in server_source
    assert 'self.one_shot == "double_jump"' in tester_source
    assert 'double_jump_scale_multiplier' in tester_source

    print("MULTIPLAYER MOVEMENT AUDIT: PASS")
    print("Shift run, authoritative jump/double-jump, prone landing, stand controls and preview scaling are integrated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
