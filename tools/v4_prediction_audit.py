from __future__ import annotations

import math
import sys
from collections import deque
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from client import Game, MOVEMENT_FLAG_IN_VEHICLE, RemotePlayer


def make_game() -> tuple[Game, RemotePlayer]:
    game = Game.__new__(Game)
    game.settings = {
        "movement": {
            "walk_speed_px_per_second": 100.0,
            "sprint_multiplier": 2.0,
            "water_walk_speed_multiplier": 0.25,
        }
    }
    game.grid_world = None
    game.map_config = {
        "world_w": 1000,
        "world_h": 1000,
        "chunked": False,
        "buildings": [],
        "water": [],
        "roads": [],
        "level_connectors": [],
    }
    game.local_id = "local"
    player = RemotePlayer({
        "id": "local", "name": "Local", "x": 100.0, "y": 100.0,
    })
    game.players = {"local": player}
    game.interior = SimpleNamespace(active=False)
    game.pending_predicted_inputs = []
    game.last_prediction_sample = 1.0
    game.prediction_error = 0.0
    game.prediction_corrections = 0
    game.prediction_snap_distance = 96.0
    return game, player


def main() -> int:
    game, player = make_game()

    game.record_and_apply_on_foot_prediction(
        0, 1.0, 0.0, False, False, False, False, 1.02
    )
    assert math.isclose(player.render_x, 102.0, abs_tol=1e-6)
    assert math.isclose(player.target_x, 102.0, abs_tol=1e-6)
    assert [sample["sequence"] for sample in game.pending_predicted_inputs] == [0]

    game.record_and_apply_on_foot_prediction(
        1, 1.0, 0.0, False, False, False, False, 1.04
    )
    assert math.isclose(player.render_x, 104.0, abs_tol=1e-6)
    game.reconcile_local_on_foot(
        player, 101.9, 100.0, 100.0, 0.0, 0.0, 0, 0, 0
    )
    assert [sample["sequence"] for sample in game.pending_predicted_inputs] == [1]
    assert math.isclose(player.target_x, 103.9, abs_tol=1e-6)
    assert 0.09 < game.prediction_error < 0.11
    assert game.prediction_corrections == 0

    # A correction larger than the safety threshold must snap instead of
    # visibly sliding across the world from a teleport or severe desync.
    game.pending_predicted_inputs.clear()
    player.render_x, player.render_y = 500.0, 500.0
    game.reconcile_local_on_foot(
        player, 120.0, 140.0, 0.0, 0.0, 0.0, 0, 0, 1
    )
    assert (player.render_x, player.render_y) == (120.0, 140.0)
    assert game.prediction_corrections == 1

    # Prediction uses the shared circle/building collision path.
    game.map_config["buildings"] = [(125.0, 70.0, 30.0, 60.0)]
    blocked_x, blocked_y = game.predict_on_foot_step(
        100.0, 100.0, 1.0, 0.0, False, 0.1, 0
    )
    assert (blocked_x, blocked_y) == (100.0, 100.0)

    # Entering a vehicle clears pedestrian replay and returns position ownership
    # to the authoritative vehicle stream.
    game.pending_predicted_inputs = [{"sequence": 2}]
    game.reconcile_local_on_foot(
        player, 220.0, 240.0, 35.0, 0.0, 0.0,
        MOVEMENT_FLAG_IN_VEHICLE, 0, 2,
    )
    assert game.pending_predicted_inputs == []
    assert player.in_vehicle
    assert (player.target_x, player.target_y) == (220.0, 240.0)

    print("V4 ON-FOOT PREDICTION AUDIT: PASS")
    print("  immediate input + ack replay + collision + desync snap + vehicle handoff verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
