from __future__ import annotations

"""v1.0 grid-authoritative desktop client entry.

This entry keeps the legacy client available for old servers while making the
active v1.0 Ground runtime visually exclusive: no retired vector/elevated map
geometry is allowed to render on top of GridWorld.  It also applies the
player-scale correction required by the 256 px grid art.
"""

import asyncio

import client as game_client


_ORIGINAL_DRAW_WORLD = game_client.Game.draw_world
_ORIGINAL_DRAW_PLAYER = game_client.Game.draw_player
_ORIGINAL_DRAW_NAMEPLATES = game_client.Game.draw_player_nameplates


def _grid_ground_active(game: game_client.Game) -> bool:
    if getattr(game, "grid_renderer", None) is None:
        return False
    local = game.players.get(game.local_id or "")
    level = int(getattr(local, "level", 0)) if local is not None else 0
    return level == 0


def _draw_world_grid_exclusive(game: game_client.Game) -> None:
    """Render exactly one Ground authority when the v1.0 grid is active."""
    if not _grid_ground_active(game):
        _ORIGINAL_DRAW_WORLD(game)
        return
    game.grid_renderer.draw_view(game.screen, game.camera(), "ground")


def _with_grid_player_scale(game: game_client.Game, callback, *args, **kwargs):
    if not _grid_ground_active(game):
        return callback(game, *args, **kwargs)
    render = game.settings.setdefault("render", {})
    previous = render.get("player_scale", 1)
    # The legacy avatar was authored for the old small vector-map scale.  At the
    # 256 px v1.0 tile scale, 2x restores the intended player-to-street ratio.
    render["player_scale"] = max(2, int(previous or 1))
    try:
        return callback(game, *args, **kwargs)
    finally:
        render["player_scale"] = previous


def _draw_player_grid_scale(game: game_client.Game, player, local: bool) -> None:
    return _with_grid_player_scale(game, _ORIGINAL_DRAW_PLAYER, player, local)


def _draw_nameplates_grid_scale(game: game_client.Game) -> None:
    return _with_grid_player_scale(game, _ORIGINAL_DRAW_NAMEPLATES)


def _suppress_legacy_elevated_overlay(*_args, **_kwargs) -> None:
    """No retired bridge/upper-road overlay may bleed into v1.0 Ground."""
    return None


game_client.Game.draw_world = _draw_world_grid_exclusive
game_client.Game.draw_player = _draw_player_grid_scale
game_client.Game.draw_player_nameplates = _draw_nameplates_grid_scale
game_client.EnvironmentRenderer.draw_elevated_overlay = _suppress_legacy_elevated_overlay


if __name__ == "__main__":
    asyncio.run(game_client.main())
