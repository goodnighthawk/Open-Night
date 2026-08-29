from __future__ import annotations


DEFAULT_GAME_MODE_ID = "glorious_car_hijacker"

GAME_MODES: dict[str, dict[str, str]] = {
    DEFAULT_GAME_MODE_ID: {
        "id": DEFAULT_GAME_MODE_ID,
        "name": "Glorious Car Hijacker",
        "description": "The original Open Night shared-city gameplay mode.",
    },
}


def get_game_mode(mode_id: str | None = None) -> dict[str, str]:
    """Resolve a supported mode without silently inventing a ruleset."""
    wanted = str(mode_id or DEFAULT_GAME_MODE_ID).strip().lower()
    return dict(GAME_MODES.get(wanted, GAME_MODES[DEFAULT_GAME_MODE_ID]))
