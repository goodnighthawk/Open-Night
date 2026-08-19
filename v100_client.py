from __future__ import annotations

"""Canonical Open Night v1.0 desktop/web client entry.

The legacy client module remains the implementation library for mature gameplay
features. v1.0 installs the curb-safe GridWorld refinement and shared 0.5x world
normalization before importing the client so rendering/collision/network geometry
all see the same authoritative scale.
"""

import asyncio

import v100_runtime_refinement
import v100_safe_layout
v100_safe_layout.install(v100_runtime_refinement)
v100_runtime_refinement.install()
import v100_scale_normalization
v100_scale_normalization.install()

import grid_client_entry  # noqa: F401 - installs the v1.0 GridWorld cutover
import client as game_client
import bug_chat_shortcut
import portrait_head_client


def install_v100_client() -> None:
    v100_safe_layout.install(v100_runtime_refinement)
    v100_runtime_refinement.install()
    v100_scale_normalization.install()
    portrait_head_client._install()
    bug_chat_shortcut.install()


async def main() -> None:
    install_v100_client()
    await game_client.main()


if __name__ == "__main__":
    asyncio.run(main())
