"""Single source of truth for the multiplayer wire/build version."""

GAME_VERSION = "1.9"


def version_label() -> str:
    return f"Open Night v{GAME_VERSION}"
