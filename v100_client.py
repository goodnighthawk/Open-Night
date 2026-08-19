from __future__ import annotations

"""Canonical Open Night v1.0 desktop/web client entry.

The legacy client module remains the implementation library for mature gameplay
features. Importing grid_client_entry replaces only retired map authority/render
surfaces with GridWorld. The portrait selector is then installed on top so the
existing character customization feature is preserved.
"""

import asyncio

import grid_client_entry  # noqa: F401 - installs the v1.0 GridWorld cutover
import client as game_client
import portrait_head_client


def install_v100_client() -> None:
    portrait_head_client._install()


async def main() -> None:
    install_v100_client()
    await game_client.main()


if __name__ == "__main__":
    asyncio.run(main())
