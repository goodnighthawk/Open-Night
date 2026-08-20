from __future__ import annotations

"""Canonical Open Night v1.1 desktop/web client entry.

The legacy client module remains the implementation library for mature gameplay
features. v1.0 installed the curb-safe GridWorld refinement and shared 0.5x world
normalization; v1.1 retains that authority and adds the current bug-review and
multiplayer version gates before entering the mature client runtime.
"""

import asyncio

import v100_runtime_refinement
import v100_safe_layout
v100_safe_layout.install(v100_runtime_refinement)
v100_runtime_refinement.install()
import v100_scale_normalization
v100_scale_normalization.install()

import grid_client_entry  # noqa: F401 - installs the GridWorld cutover
import client as game_client
import bug_chat_shortcut
import portrait_head_client
import v110_version_client


def install_v100_client() -> None:
    v100_safe_layout.install(v100_runtime_refinement)
    v100_runtime_refinement.install()
    v100_scale_normalization.install()
    portrait_head_client._install()
    bug_chat_shortcut.install()
    v110_version_client.install(game_client)


async def main() -> None:
    install_v100_client()
    await game_client.main()


if __name__ == "__main__":
    asyncio.run(main())
