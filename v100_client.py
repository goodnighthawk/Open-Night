from __future__ import annotations

"""Canonical Open Night v1.1 desktop/web client entry.

The legacy client module remains the implementation library for mature gameplay
features. v1.0 installed the curb-safe GridWorld refinement and shared 0.5x world
normalization; v1.1 retains that authority and adds bug-review reliability and
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
import v110_bug_delivery_client
import v110_bug_railway_relay_client
import v110_job_locations
import v110_population_render
import v110_version_client


def install_v100_client() -> None:
    v100_safe_layout.install(v100_runtime_refinement)
    v100_runtime_refinement.install()
    v100_scale_normalization.install()
    portrait_head_client._install()
    bug_chat_shortcut.install()
    v110_version_client.install(game_client)
    # Normalize gameplay destinations as soon as the canonical GridWorld has
    # been attached to the Game instance, before map/minimap interaction uses them.
    v110_job_locations.install_client(game_client)
    v110_population_render.install(game_client)
    # GridWorld Ground already guarantees a 2x player render. Ambient people
    # must share that minimum or stale/default settings recreate the half-sized
    # NPC regression reported in v1.1 playtests.
    if v110_population_render.effective_npc_scale(
        {"render": {"player_scale": 1, "npc_scale": 1}}, grid_ground=True
    ) < 2.0:
        raise RuntimeError("v1.1 Ground NPC scale contract is below the player minimum")
    v110_bug_delivery_client.install(game_client)
    # Reports always target the public Railway review service, independent of
    # whichever local/LAN/internet server is carrying gameplay.
    v110_bug_railway_relay_client.install(game_client)


async def main() -> None:
    install_v100_client()
    await game_client.main()


if __name__ == "__main__":
    asyncio.run(main())
