from __future__ import annotations

from common import PlayerState, empty_inventory
from game_modes import DEFAULT_GAME_MODE_ID, get_game_mode
from housing_spawn import blank_house_interiors
import server


class _Socket:
    remote_address = ("127.0.0.1", 0)


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

    house = blank_house_interiors(server.ACTIVE_MAP)[0]
    apartment_id = str(house["id"])
    entry_x, entry_y = map(float, house["entry"])
    resident = _session("ResidentX", "15550000001", apartment_id, entry_x, entry_y, active_interior=apartment_id)
    stranger = _session("Stranger", "15550000002", "", entry_x + 1000.0, entry_y + 1000.0)
    friend = _session("Friend", "15550000003", "", entry_x + 1000.0, entry_y + 1000.0, friends={"residentx"})
    buzzer_visitor = _session("Visitor", "15550000004", "", entry_x, entry_y)
    indoor_visitor = _session("Inside", "15550000005", "", entry_x, entry_y, active_interior="another_room")

    assert server._can_view_apartment_residency(resident, resident), "a resident must see their own listing"
    assert server._can_view_apartment_residency(friend, resident), "saved friends must see the resident listing"
    assert server._can_view_apartment_residency(buzzer_visitor, resident), "a nearby buzzer visitor must see the listing"
    assert not server._can_view_apartment_residency(stranger, resident), "distant strangers must not see residency"
    assert not server._can_view_apartment_residency(indoor_visitor, resident), "buzzer access requires standing outside"
    assert server.normalize_friend_names([" ResidentX ", "", "bad!name"]) == {"residentx", "badname"}

    info = server.server_info_payload("Test", 8765, 30, server.ACTIVE_MAP)
    assert info["game_mode_id"] == DEFAULT_GAME_MODE_ID
    assert info["game_mode_name"] == "Glorious Car Hijacker"
    print("v4 server contract OK: Glorious Car Hijacker + private apartment buzzer directory")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
