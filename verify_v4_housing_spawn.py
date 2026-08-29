from __future__ import annotations

from pathlib import Path

from housing_spawn import blank_house_interiors, house_login_state, house_spawn_state, select_house_for_account
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

    shared_account = "shared-home-check"
    chosen = select_house_for_account(cfg, shared_account)
    assert chosen is not None
    assert select_house_for_account(cfg, shared_account) == chosen, "an account must always return to its usual shared home"

    login_state = house_login_state(cfg, shared_account)
    assert login_state is not None, "shared home login state must be available"
    room_id, exterior_x, exterior_y, tile_x, tile_y = login_state
    assert room_id == str(chosen["id"]), "login room must match the account's usual home"
    assert (exterior_x, exterior_y) == tuple(map(float, chosen["entry"])), "exit must use the home's exterior entrance"
    assert (tile_x, tile_y) == house_spawn_state(cfg, shared_account)[1:], "login must use the first-floor start tile"

    used_ids = {str(state[0]) for state in first_pass if state is not None}
    assert len(used_ids) >= 10, f"account hashing is not distributing houses well enough: {len(used_ids)} used"

    print(f"v4 housing-spawn foundation OK: {len(houses)} houses, {len(used_ids)} used by 100 sample accounts, districts={districts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
