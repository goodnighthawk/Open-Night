from __future__ import annotations

import asyncio
import json
import math
from pathlib import Path

from common import (
    NETWORK_ZONE_RADIUS,
    NETWORK_ZONE_SIZE,
    PlayerState,
    SERVER_TICK_RATE,
    SNAPSHOT_RATE,
    dequantize_movement_angle,
    dequantize_movement_position,
    empty_inventory,
    quantize_movement_angle,
    quantize_movement_position,
    subscribed_network_zones,
    world_to_network_zone,
)
from game_modes import DEFAULT_GAME_MODE_ID, get_game_mode
from housing_spawn import blank_house_interiors, reserved_house_login_state
import server


class _Socket:
    remote_address = ("127.0.0.1", 0)

    def __init__(self) -> None:
        self.messages: list[str] = []

    async def send(self, raw: str) -> None:
        self.messages.append(raw)


async def _probe_live_tick_loop() -> dict:
    server.SERVER_TICK_METRICS = server.ServerTickMetrics(SERVER_TICK_RATE)
    task = asyncio.create_task(server.simulation_loop())
    await asyncio.sleep(1.25)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    return server.SERVER_TICK_METRICS.public_dict()


async def _probe_movement_stream(session: server.ClientSession) -> list[dict]:
    previous_clients = dict(server.clients)
    server.clients.clear()
    server.clients[session.player.player_id] = session
    task = asyncio.create_task(server.movement_stream_loop())
    await asyncio.sleep(0.07)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    server.clients.clear()
    server.clients.update(previous_clients)
    return [json.loads(raw) for raw in session.websocket.messages]


def _session(
    name: str,
    phone: str,
    apartment_id: str,
    x: float,
    y: float,
    *,
    active_interior: str = "",
    friends: set[str] | None = None,
) -> server.ClientSession:
    player = PlayerState(
        player_id=phone[-8:],
        name=name,
        x=x,
        y=y,
        interior_id=active_interior,
    )
    return server.ClientSession(
        websocket=_Socket(),
        player=player,
        phone=phone,
        inventory=empty_inventory(),
        apartment_interior_id=apartment_id,
        friend_names=set(friends or set()),
    )


def main() -> int:
    mode = get_game_mode()
    assert mode["id"] == DEFAULT_GAME_MODE_ID == "glorious_car_hijacker"
    assert mode["name"] == "Glorious Car Hijacker"
    assert SERVER_TICK_RATE == 60
    assert SNAPSHOT_RATE == 20
    assert server.AMBIENT_SIM_RATE == 30.0
    assert server.MAX_PLAYERS == 64
    assert server.MOVEMENT_STREAM_RATE == 60.0
    assert NETWORK_ZONE_SIZE == 3072
    assert NETWORK_ZONE_RADIUS == 1
    assert server.ACTIVE_MAP["network_zone_size"] == 3072
    assert server.ACTIVE_MAP["network_zone_radius"] == 1
    assert world_to_network_zone(3071.99, 3071.99, server.ACTIVE_MAP) == (0, 0)
    assert world_to_network_zone(3072.0, 3072.0, server.ACTIVE_MAP) == (1, 1)
    central_zones = subscribed_network_zones(4608.0, 4608.0, server.ACTIVE_MAP)
    assert len(central_zones) == len(set(central_zones)) == 9
    assert set(central_zones) == {(x, y) for y in range(0, 3) for x in range(0, 3)}
    edge_zones = subscribed_network_zones(0.0, 0.0, server.ACTIVE_MAP)
    assert len(edge_zones) == len(set(edge_zones)) == 9
    oversized_radius_map = dict(server.ACTIVE_MAP, network_zone_radius=4)
    assert len(subscribed_network_zones(4608.0, 4608.0, oversized_radius_map)) == 9
    assert dequantize_movement_position(quantize_movement_position(123.37)) == 123.25
    angle = dequantize_movement_angle(quantize_movement_angle(-0.75))
    assert abs(math.atan2(math.sin(angle + 0.75), math.cos(angle + 0.75))) < 0.001

    metrics = server.ServerTickMetrics(SERVER_TICK_RATE)
    started = metrics.window_started
    for tick in range(60):
        completed = started + (tick + 1) / 60.0 + (0.001 if tick == 59 else 0.0)
        metrics.record_tick(0.002, completed)
    measured = metrics.public_dict()
    assert 59.0 <= measured["server_tick_rate_hz"] <= 61.0
    assert measured["server_tick_time_ms"] == 2.0
    assert measured["server_tick_configured_rate_hz"] == 60

    live_metrics = asyncio.run(_probe_live_tick_loop())
    assert 55.0 <= live_metrics["server_tick_rate_hz"] <= 65.0, live_metrics
    assert live_metrics["server_tick_time_ms"] < live_metrics["server_tick_budget_ms"], live_metrics

    house = blank_house_interiors(server.ACTIVE_MAP)[0]
    apartment_id = str(house["id"])
    reserved_login = reserved_house_login_state(server.ACTIVE_MAP, apartment_id)
    assert reserved_login is not None and reserved_login[0] == apartment_id
    entry_x, entry_y = map(float, house["entry"])
    resident = _session("ResidentX", "15550000001", apartment_id, entry_x, entry_y, active_interior=apartment_id)
    stranger = _session("Stranger", "15550000002", "", entry_x + 1000.0, entry_y + 1000.0)
    friend = _session("Friend", "15550000003", "", entry_x + 1000.0, entry_y + 1000.0, friends={"residentx"})
    resident.friend_names.add("friend")
    one_sided = _session("OneSided", "15550000006", "", entry_x + 1000.0, entry_y + 1000.0, friends={"residentx"})
    buzzer_visitor = _session("Visitor", "15550000004", "", entry_x, entry_y)
    indoor_visitor = _session("Inside", "15550000005", "", entry_x, entry_y, active_interior="another_room")

    input_session = _session("Sequenced", "15550000007", "", entry_x, entry_y)
    asyncio.run(server.handle_message(input_session, json.dumps({
        "type": "input", "sequence": 2, "x": 0.5, "y": 0.0, "aim": 0.0,
    })))
    assert input_session.last_received_input_sequence == 2
    assert input_session.input_x == 0.5
    asyncio.run(server.handle_message(input_session, json.dumps({
        "type": "input", "sequence": 1, "x": -1.0, "y": 0.0, "aim": 0.0,
    })))
    assert input_session.last_received_input_sequence == 2
    assert input_session.input_x == 0.5, "stale input must not replace newer authoritative intent"
    asyncio.run(server.handle_message(input_session, json.dumps({
        "type": "input", "sequence": 5, "x": 0.0, "y": 1.0, "aim": 0.0,
    })))
    assert input_session.last_received_input_sequence == 5, "unreliable input gaps must be accepted"
    input_session.last_processed_input_sequence = 5
    movement_record = server.movement_player_record(input_session, 0.0, {}, {})
    assert len(movement_record) == 8
    assert movement_record[0] == input_session.player.player_id
    assert abs(dequantize_movement_position(movement_record[1]) - input_session.player.x) <= 0.125
    movement_messages = asyncio.run(_probe_movement_stream(input_session))
    assert len(movement_messages) >= 3
    assert all(message["type"] == "movement" for message in movement_messages)
    assert movement_messages[-1]["a"] == 5
    assert movement_messages[-1]["p"][0][0] == input_session.player.player_id
    assert len(json.dumps(movement_messages[-1], separators=(",", ":"))) < 256
    asyncio.run(server.handle_message(input_session, json.dumps({
        "type": "network_probe", "id": 37,
    })))
    probe_ack = json.loads(input_session.websocket.messages[-1])
    assert probe_ack == {"type": "network_probe_ack", "id": 37}

    assert server._can_view_apartment_residency(resident, resident), "a resident must see their own listing"
    assert server._can_view_apartment_residency(friend, resident), "mutually accepted friends must see the resident listing"
    offline_reservation = server.ApartmentReservation(
        account_key=resident.phone,
        interior_id=resident.apartment_interior_id,
        resident_name=resident.player.name,
    )
    assert not server._can_view_apartment_reservation(friend, offline_reservation, None), (
        "offline residents require buzzer proximity because reciprocal device-local friendship cannot be verified"
    )
    assert server._can_view_apartment_reservation(buzzer_visitor, offline_reservation, None), (
        "offline reservations must remain visible at their buzzer"
    )
    assert not server._can_view_apartment_residency(one_sided, resident), "one-sided friend requests must not reveal residency"
    assert server._can_view_apartment_residency(buzzer_visitor, resident), "a nearby buzzer visitor must see the listing"
    assert not server._can_view_apartment_residency(stranger, resident), "distant strangers must not see residency"
    assert not server._can_view_apartment_residency(indoor_visitor, resident), "buzzer access requires standing outside"
    assert server.normalize_friend_names([" ResidentX ", "", "bad!name"]) == {"residentx", "badname"}

    info = server.server_info_payload("Test", 8765, server.MAX_PLAYERS, server.ACTIVE_MAP)
    assert info["game_mode_id"] == DEFAULT_GAME_MODE_ID
    assert info["game_mode_name"] == "Glorious Car Hijacker"
    assert info["housing_capacity"] == 32
    assert info["max_players"] == 64
    assert info["server_metrics"]["server_tick_configured_rate_hz"] == 60
    assert info["network_zone_size"] == 3072
    assert info["network_zone_radius"] == 1
    assert info["network_zone_subscription_count"] == 9

    client_source = (Path(__file__).resolve().parent / "client.py").read_text(encoding="utf-8")
    for token in ("SERVER POPULATION", "server_population", "housing_capacity", "(255, 72, 72)",
                  "NETWORK_SEND_RATE = 60", "draw_network_debug_overlay", "pygame.K_F8",
                  '"sequence": self.next_input_sequence()', "last_processed_input_sequence",
                  "process_movement_packet", "server_movement_rate",
                  "pending_predicted_inputs", "predict_on_foot_step",
                  "reconcile_local_on_foot", "prediction_error",
                  "update_network_telemetry", "network_probe",
                  "movement_loss_percent", "network_inbound_bytes_per_second"):
        assert token in client_source, f"population HUD contract missing {token}"
    launcher_source = (Path(__file__).resolve().parent / "server_launcher.py").read_text(encoding="utf-8")
    assert '"max_players": 64' in launcher_source
    stress_source = (Path(__file__).resolve().parent / "tools" / "stress_test_bots.py").read_text(encoding="utf-8")
    for token in ("network_zones_covered", "server_tick_p05_hz", "movement_loss_percent",
                  "evaluate_v4_city_proof", "apartment_exit_requests"):
        assert token in stress_source, f"v4 city load contract missing {token}"
    assert (Path(__file__).resolve().parent / "RUN_V4_CITY_LOAD_TEST.bat").is_file()
    housing_audit = Path(__file__).resolve().parent / "tools" / "v4_housing_network_audit.py"
    housing_source = housing_audit.read_text(encoding="utf-8")
    for token in ("distinct_apartments", "one_sided_privacy", "mutual_friend_directory",
                  "buzzer_directory", "exit_reentry", "offline_buzzer_reservation",
                  "reservation_blocks_reassignment", "reservation_reconnect"):
        assert token in housing_source, f"v4 housing network audit missing {token}"
    assert (Path(__file__).resolve().parent / "RUN_V4_HOUSING_TEST.bat").is_file()
    session_audit = Path(__file__).resolve().parent / "tools" / "multiplayer_map_roster_audit.py"
    session_source = session_audit.read_text(encoding="utf-8")
    for token in ("outdated", "outdoor_pair", "movement_pair",
                  "disconnected player removal", "reconnect_apartment",
                  "reconnected indoor player redaction"):
        assert token in session_source, f"v4 multiplayer session audit missing {token}"
    assert (Path(__file__).resolve().parent / "RUN_V4_MULTIPLAYER_SESSION_TEST.bat").is_file()
    prediction_audit = Path(__file__).resolve().parent / "tools" / "v4_prediction_audit.py"
    prediction_source = prediction_audit.read_text(encoding="utf-8")
    for token in ("record_and_apply_on_foot_prediction", "reconcile_local_on_foot",
                  "pending_predicted_inputs", "prediction_snap_distance",
                  "MOVEMENT_FLAG_IN_VEHICLE"):
        assert token in prediction_source, f"v4 prediction audit missing {token}"
    vehicle_audit = Path(__file__).resolve().parent / "tools" / "v4_vehicle_authority_audit.py"
    vehicle_source = vehicle_audit.read_text(encoding="utf-8")
    for token in ("SERVER_TICK_RATE == 60", "MOVEMENT_STREAM_RATE, 60.0",
                  "vehicle.target_x", "vehicle.smooth(1.0 / 60.0)",
                  "simulate_render_rate(120)"):
        assert token in vehicle_source, f"v4 vehicle authority audit missing {token}"
    print("v4 server contract OK: 60 Hz authority + 3x3 zones + prediction/telemetry + housing/privacy")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
