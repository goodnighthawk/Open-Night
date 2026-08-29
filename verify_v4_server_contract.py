from __future__ import annotations

import asyncio
from pathlib import Path

from common import (
    NETWORK_ZONE_RADIUS,
    NETWORK_ZONE_SIZE,
    PlayerState,
    SERVER_TICK_RATE,
    SNAPSHOT_RATE,
    empty_inventory,
    subscribed_network_zones,
    world_to_network_zone,
)
from game_modes import DEFAULT_GAME_MODE_ID, get_game_mode
from housing_spawn import blank_house_interiors
import server


class _Socket:
    remote_address = ("127.0.0.1", 0)


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
    entry_x, entry_y = map(float, house["entry"])
    resident = _session("ResidentX", "15550000001", apartment_id, entry_x, entry_y, active_interior=apartment_id)
    stranger = _session("Stranger", "15550000002", "", entry_x + 1000.0, entry_y + 1000.0)
    friend = _session("Friend", "15550000003", "", entry_x + 1000.0, entry_y + 1000.0, friends={"residentx"})
    resident.friend_names.add("friend")
    one_sided = _session("OneSided", "15550000006", "", entry_x + 1000.0, entry_y + 1000.0, friends={"residentx"})
    buzzer_visitor = _session("Visitor", "15550000004", "", entry_x, entry_y)
    indoor_visitor = _session("Inside", "15550000005", "", entry_x, entry_y, active_interior="another_room")

    assert server._can_view_apartment_residency(resident, resident), "a resident must see their own listing"
    assert server._can_view_apartment_residency(friend, resident), "mutually accepted friends must see the resident listing"
    assert not server._can_view_apartment_residency(one_sided, resident), "one-sided friend requests must not reveal residency"
    assert server._can_view_apartment_residency(buzzer_visitor, resident), "a nearby buzzer visitor must see the listing"
    assert not server._can_view_apartment_residency(stranger, resident), "distant strangers must not see residency"
    assert not server._can_view_apartment_residency(indoor_visitor, resident), "buzzer access requires standing outside"
    assert server.normalize_friend_names([" ResidentX ", "", "bad!name"]) == {"residentx", "badname"}

    info = server.server_info_payload("Test", 8765, server.MAX_PLAYERS, server.ACTIVE_MAP)
    assert info["game_mode_id"] == DEFAULT_GAME_MODE_ID
    assert info["game_mode_name"] == "Glorious Car Hijacker"
    assert info["housing_capacity"] == 14
    assert info["max_players"] == 64
    assert info["server_metrics"]["server_tick_configured_rate_hz"] == 60
    assert info["network_zone_size"] == 3072
    assert info["network_zone_radius"] == 1
    assert info["network_zone_subscription_count"] == 9

    client_source = (Path(__file__).resolve().parent / "client.py").read_text(encoding="utf-8")
    for token in ("SERVER POPULATION", "server_population", "housing_capacity", "(255, 72, 72)",
                  "NETWORK_SEND_RATE = 60", "draw_network_debug_overlay", "pygame.K_F8"):
        assert token in client_source, f"population HUD contract missing {token}"
    launcher_source = (Path(__file__).resolve().parent / "server_launcher.py").read_text(encoding="utf-8")
    assert '"max_players": 64' in launcher_source
    print("v4 server contract OK: 60 Hz authority + dedicated 3x3 network zones + housing/privacy")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
