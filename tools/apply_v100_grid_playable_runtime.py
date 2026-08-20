#!/usr/bin/env python3
"""Promote the v1.0 authored grid into the existing multiplayer runtime.

The patch is intentionally narrow and idempotent. Ground/level 0 switches to the
GridWorld/GridRenderer contract; nonzero legacy levels remain available during the
migration. Legacy traffic/NPC surface entities are disabled because their old CSV
routes do not describe the rewritten grid map.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        return text
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one anchor, found {count}")
    return text.replace(old, new, 1)


def patch_server() -> None:
    path = ROOT / "server.py"
    text = path.read_text(encoding="utf-8")

    text = replace_once(
        text,
        "from versioning import GAME_VERSION\n",
        "from versioning import GAME_VERSION\nfrom grid_runtime import ground_grid_enabled, load_ground_grid, grid_network_metadata\n",
        "server grid import",
    )
    text = replace_once(
        text,
        "ACTIVE_MAP = get_map(ACTIVE_MAP_ID)\nACTIVE_MAP_TRANSFER = None\n",
        "ACTIVE_MAP = get_map(ACTIVE_MAP_ID)\nGRID_RUNTIME_ACTIVE = ground_grid_enabled(ACTIVE_MAP)\nGRID_WORLD = load_ground_grid() if GRID_RUNTIME_ACTIVE else None\nACTIVE_MAP_TRANSFER = None\n",
        "server grid singleton",
    )
    text = replace_once(
        text,
        '        out["map_payload_mode"] = "local_chunked_v1"\n        return out\n',
        '        out["map_payload_mode"] = "local_chunked_v1"\n        out.update(grid_network_metadata(map_config))\n        return out\n',
        "server map payload",
    )
    text = replace_once(
        text,
        "def choose_safe_player_spawn(map_config: dict) -> tuple[float, float]:\n",
        "def choose_safe_player_spawn(map_config: dict) -> tuple[float, float]:\n    if GRID_RUNTIME_ACTIVE and GRID_WORLD is not None:\n        return GRID_WORLD.choose_spawn(\"ground\", PLAYER_RADIUS)\n",
        "server grid spawn",
    )
    text = replace_once(
        text,
        "            wading = current_level == 0 and (\n",
        "            wading = (not GRID_RUNTIME_ACTIVE) and current_level == 0 and (\n",
        "server disable legacy water probe",
    )
    text = replace_once(
        text,
        "            p.x, p.y = move_with_collisions(\n                p.x, p.y, dx, dy, ACTIVE_MAP, level=current_level, allow_water=True\n            )\n",
        "            if GRID_RUNTIME_ACTIVE and GRID_WORLD is not None and current_level == 0:\n                p.x, p.y = GRID_WORLD.move_circle(\n                    \"ground\", p.x, p.y, dx, dy, PLAYER_RADIUS\n                )\n            else:\n                p.x, p.y = move_with_collisions(\n                    p.x, p.y, dx, dy, ACTIVE_MAP, level=current_level, allow_water=True\n                )\n",
        "server grid movement",
    )
    text = replace_once(
        text,
        "            p.level = next_level\n            if next_level != previous_level and LAYER_TRANSITION_JUMP_SECONDS > 0.0:\n",
        "            if GRID_RUNTIME_ACTIVE and previous_level == 0:\n                # Grid Ground owns its own future transition cells. Do not let the\n                # retired vector connector table switch levels underneath it.\n                next_level = 0\n            p.level = next_level\n            if next_level != previous_level and LAYER_TRANSITION_JUMP_SECONDS > 0.0:\n",
        "server suppress legacy ground transitions",
    )
    text = replace_once(
        text,
        "    initialize_traffic(TRAFFIC_COUNT)\n    initialize_parked_vehicles()\n    initialize_bicycles()\n    initialize_npcs()\n    initialize_hydrants()\n",
        "    if GRID_RUNTIME_ACTIVE:\n        # Old entity routes were authored against the retired vector map and may\n        # cross new buildings. Keep the first playable grid milestone honest by\n        # suppressing them until grid-native routes/spawns are authored.\n        print(\"Grid Ground runtime active: legacy traffic/NPC surface entities disabled.\")\n    else:\n        initialize_traffic(TRAFFIC_COUNT)\n        initialize_parked_vehicles()\n        initialize_bicycles()\n        initialize_npcs()\n        initialize_hydrants()\n",
        "server legacy entity initialization",
    )

    path.write_text(text, encoding="utf-8")


def patch_client() -> None:
    path = ROOT / "client.py"
    text = path.read_text(encoding="utf-8")

    text = replace_once(
        text,
        "from environment_art import EnvironmentRenderer\n",
        "from environment_art import EnvironmentRenderer\nfrom grid_renderer import GridRenderer\nfrom grid_runtime import ground_grid_enabled, load_ground_grid\n",
        "client grid imports",
    )
    text = replace_once(
        text,
        "        self.environment = EnvironmentRenderer(self.map_config)\n",
        "        self.environment = EnvironmentRenderer(self.map_config)\n        self.grid_world = load_ground_grid() if ground_grid_enabled(self.map_config) else None\n        self.grid_renderer = GridRenderer(self.grid_world) if self.grid_world is not None else None\n",
        "client grid initialization",
    )
    text = replace_once(
        text,
        "        self.environment.set_active_level(active_world_level)\n        self.environment.draw_view(self.screen, self.camera())\n",
        "        if active_world_level == 0 and self.grid_renderer is not None:\n            self.grid_renderer.draw_view(self.screen, self.camera(), \"ground\")\n        else:\n            self.environment.set_active_level(active_world_level)\n            self.environment.draw_view(self.screen, self.camera())\n",
        "client grid ground render",
    )

    path.write_text(text, encoding="utf-8")


def main() -> None:
    patch_server()
    patch_client()
    print("V100_GRID_PLAYABLE_PATCH_OK")


if __name__ == "__main__":
    main()
