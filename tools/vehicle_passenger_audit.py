from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import server
from common import PlayerState, empty_inventory


class CaptureSocket:
    def __init__(self) -> None:
        self.messages: list[dict] = []

    async def send(self, raw: str) -> None:
        self.messages.append(json.loads(raw))


async def exercise() -> None:
    x, y = server.choose_safe_player_spawn(server.ACTIVE_MAP)
    car = server.TrafficVehicle(
        vehicle_id="passenger-audit-car", route_index=-1, next_waypoint=0,
        x=x, y=y, angle=0.0, speed=0.0, color_index=0, sprite_index=0,
        controlled_by="", npc_driver=False, parked=True,
    )
    server.traffic_vehicles[:] = [car]
    server.bicycles.clear()

    driver_player = PlayerState("audit-driver", "Driver", x, y)
    rider_player = PlayerState("audit-passenger", "Passenger", x, y)
    driver = server.ClientSession(CaptureSocket(), driver_player, "15557770001", empty_inventory())
    passenger = server.ClientSession(CaptureSocket(), rider_player, "15557770002", empty_inventory())

    await server.process_car_action(driver)
    assert driver.driving_vehicle_id == car.vehicle_id
    assert driver_player.vehicle_role == "driver"
    assert car.controlled_by == driver_player.player_id

    await server.process_car_action(passenger)
    assert passenger.passenger_vehicle_id == car.vehicle_id
    assert rider_player.vehicle_role == "passenger"
    assert rider_player.player_id in car.passenger_ids
    public = car.public_dict()
    assert public["passengers"] == 1
    assert public["passenger_capacity"] == server.PASSENGER_CAPACITY

    await server.process_car_action(passenger)
    assert passenger.passenger_vehicle_id == ""
    assert not rider_player.in_vehicle
    assert rider_player.vehicle_role == ""
    assert rider_player.player_id not in car.passenger_ids

    car.speed = server.PASSENGER_BOARD_MAX_SPEED + 1.0
    rider_player.x, rider_player.y = car.x, car.y
    await server.process_car_action(passenger)
    assert passenger.passenger_vehicle_id == ""
    assert any("too fast to board" in str(message.get("text", "")) for message in passenger.websocket.messages)


def main() -> int:
    source = (ROOT / "server.py").read_text(encoding="utf-8")
    client_source = (ROOT / "client.py").read_text(encoding="utf-8")
    for token in ("passenger_vehicle_id", "car.passenger_ids", 'p.vehicle_role = "passenger"'):
        assert token in source, token
    for token in ("PASSENGER", "RIDE AS PASSENGER", "passenger_capacity"):
        assert token in client_source, token
    asyncio.run(exercise())
    print("VEHICLE PASSENGER AUDIT: PASS")
    print(f"  driver + passenger enter/exit + moving-car board gate / capacity={server.PASSENGER_CAPACITY}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
