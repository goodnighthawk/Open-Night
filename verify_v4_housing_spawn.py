from __future__ import annotations

from pathlib import Path

from housing_spawn import (
    blank_house_interiors,
    house_login_state,
    house_spawn_state,
    overflow_exterior_spawn,
    select_house_for_account,
)
from mapfiles.loader import load_map_folder


ROOT = Path(__file__).resolve().parent
MAP_FOLDER = ROOT / "mapfiles" / "data" / "map_001_gwb_corridor"


def main() -> int:
    cfg = load_map_folder(MAP_FOLDER, attach_grid=False)
    houses = blank_house_interiors(cfg)
    assert len(houses) == 14, f"expected 14 v4 blank houses, found {len(houses)}"

    ids = [str(row["id"]) for row in houses]
    building_ids = [str(row["building_id"]) for row in houses]
    assert len(ids) == len(set(ids)), "blank-house ids must be unique"
    assert len(building_ids) == len(set(building_ids)), "one provisional house per building"

    sprites = cfg.get("building_sprites", {}) or {}
    districts: dict[str, int] = {}
    for house in houses:
        bid = str(house["building_id"])
        assert bid in cfg.get("building_ids", []), f"missing building {bid}"
        sprite = sprites.get(bid, {})
        assert str(sprite.get("building_kind", "")) != "church_landmark", f"landmark cannot be a blank house: {bid}"
        district = str(sprite.get("district", ""))
        districts[district] = districts.get(district, 0) + 1

    assert districts.get("fort_lee", 0) >= 5, "blank houses need Fort Lee coverage"
    assert districts.get("washington_heights", 0) >= 5, "blank houses need Washington Heights coverage"

    sample_accounts = [f"account-{index:03d}" for index in range(100)]
    first_pass = [house_spawn_state(cfg, account) for account in sample_accounts]
    second_pass = [house_spawn_state(cfg, account) for account in sample_accounts]
    assert first_pass == second_pass, "account-to-house selection must be stable"
    assert all(state is not None for state in first_pass), "every sample account needs a house"

    private_account = "private-floor-check"
    chosen = select_house_for_account(cfg, private_account)
    assert chosen is not None
    assert select_house_for_account(cfg, private_account) == chosen, "an account must prefer the same private floor"

    login_state = house_login_state(cfg, private_account)
    assert login_state is not None, "private-floor login state must be available"
    room_id, exterior_x, exterior_y, tile_x, tile_y = login_state
    assert room_id == str(chosen["id"]), "login room must match the account's usual home"
    assert (exterior_x, exterior_y) == tuple(map(float, chosen["entry"])), "exit must use the home's exterior entrance"
    assert (tile_x, tile_y) == house_spawn_state(cfg, private_account)[1:], "login must use the first-floor start tile"

    occupied: set[str] = set()
    for index in range(len(houses)):
        assigned = select_house_for_account(cfg, f"concurrent-{index}", occupied)
        assert assigned is not None, f"private floor {index + 1} could not be assigned"
        assigned_id = str(assigned["id"])
        assert assigned_id not in occupied, "two connected players received the same floor"
        occupied.add(assigned_id)
    assert len(occupied) == len(houses)
    assert select_house_for_account(cfg, "overflow-player", occupied) is None, "player 15 must not share a floor"
    overflow = overflow_exterior_spawn(cfg, "overflow-player")
    assert overflow is not None and overflow in {tuple(map(float, house["entry"])) for house in houses}

    used_ids = {str(state[0]) for state in first_pass if state is not None}
    assert len(used_ids) >= 10, f"account hashing is not distributing houses well enough: {len(used_ids)} used"

    print(f"v4 housing capacity OK: {len(houses)} private first floors; overflow spawns outdoors; districts={districts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
