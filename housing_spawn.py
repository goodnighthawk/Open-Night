from __future__ import annotations

import hashlib

from interior_layout import START_TILE


BLANK_HOUSE_KIND = "blank_house"


def blank_house_interiors(map_config: dict) -> list[dict]:
    """Return the authored v4.0 blank-house pool in deterministic map order."""
    houses = [
        row for row in (map_config.get("interiors", []) or [])
        if str(row.get("kind", "")).strip().lower() == BLANK_HOUSE_KIND
        and str(row.get("id", "")).strip()
        and str(row.get("building_id", "")).strip()
    ]
    return sorted(houses, key=lambda row: str(row.get("id", "")))


def select_house_for_account(
    map_config: dict,
    account_key: str,
    occupied_interior_ids: set[str] | None = None,
) -> dict | None:
    """Choose a stable pseudo-random blank house, avoiding occupied houses when possible.

    The account key is never stored here. SHA-256 is used only to spread accounts
    across the authored house pool deterministically, which gives a returning
    player the same provisional home while keeping the layout ready for persistent
    player housing in a later release.
    """
    houses = blank_house_interiors(map_config)
    if not houses:
        return None

    key = str(account_key or "open-night-guest").encode("utf-8", "replace")
    start = int.from_bytes(hashlib.sha256(key).digest()[:8], "big") % len(houses)
    occupied = {str(value) for value in (occupied_interior_ids or set()) if str(value)}

    for offset in range(len(houses)):
        house = houses[(start + offset) % len(houses)]
        if str(house.get("id", "")) not in occupied:
            return house
    return houses[start]


def house_spawn_state(
    map_config: dict,
    account_key: str,
    occupied_interior_ids: set[str] | None = None,
) -> tuple[str, int, int] | None:
    """Return the authoritative first-floor room/tile state for login."""
    house = select_house_for_account(map_config, account_key, occupied_interior_ids)
    if house is None:
        return None
    room_id = str(house.get("id", "")).strip()
    return room_id, int(START_TILE[0]), int(START_TILE[1])
