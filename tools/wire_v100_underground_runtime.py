#!/usr/bin/env python3
"""Apply the minimal v1.0 Underground runtime-rendering integration.

This patch is intentionally exact-anchor and idempotent. It changes only:
- EnvironmentRenderer composition selection/cache keying by active map level.
- Client world/dynamic-entity visibility for negative levels.
- Map 001 runtime-wired flag/build id.
- Underground CI's contract from staged-art to runtime-wired.

Gameplay collision and level-transition semantics are not modified here.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV = ROOT / "environment_art.py"
CLIENT = ROOT / "client.py"
MAP = ROOT / "mapfiles/data/map_001_gwb_corridor/map.csv"
UNDERGROUND_WORKFLOW = ROOT / ".github/workflows/v100-underground-art.yml"


def replace_once(text: str, old: str, new: str, *, label: str, marker: str | None = None) -> tuple[str, bool]:
    if marker and marker in text:
        return text, False
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one anchor, found {count}")
    return text.replace(old, new, 1), True


def patch_environment() -> bool:
    text = ENV.read_text(encoding="utf-8")
    changed = False

    text, did = replace_once(
        text,
        "        self.chunk_cache: OrderedDict[tuple[int, int, int], pygame.Surface] = OrderedDict()\n",
        "        self.chunk_cache: OrderedDict[tuple[int, int, int, int], pygame.Surface] = OrderedDict()\n",
        label="environment chunk-cache key",
        marker="OrderedDict[tuple[int, int, int, int], pygame.Surface]",
    )
    changed |= did

    text, did = replace_once(
        text,
        "        self._composition_tile_cache: OrderedDict[tuple[str, int, int], pygame.Surface] = OrderedDict()\n        self._composition_zip: zipfile.ZipFile | None = None\n",
        "        self.active_level = 0\n        self._composition_tile_cache: OrderedDict[tuple[int, str, int, int], pygame.Surface] = OrderedDict()\n        self._composition_zip: zipfile.ZipFile | None = None\n",
        label="environment active level state",
        marker="self.active_level = 0",
    )
    changed |= did

    old_method = '''    def _composition_archive_path(self) -> Path | None:\n        raw = str(self.map_config.get("baked_composition_archive", "")).strip()\n        if not raw:\n            return None\n        requested = Path(raw)\n        candidates = [requested] if requested.is_absolute() else [Path(__file__).resolve().parent / requested]\n        if not requested.is_absolute():\n            parts = requested.parts[1:] if requested.parts and requested.parts[0] == "assets" else requested.parts\n            candidates.append(shared_assets_root().joinpath(*parts))\n        return next((path for path in candidates if path.is_file()), None)\n'''
    new_method = '''    def _uses_underground_composition(self) -> bool:\n        try:\n            underground_level = int(float(self.map_config.get("underground_level_id", -1)))\n        except (TypeError, ValueError):\n            underground_level = -1\n        wired = self.map_config.get("underground_runtime_wired", False)\n        if isinstance(wired, str):\n            wired = wired.strip().lower() in {"1", "true", "yes", "on"}\n        return bool(wired) and int(self.active_level) == underground_level\n\n    def set_active_level(self, level: int) -> None:\n        """Select the visual composition for the local player's authoritative level."""\n        try:\n            level = int(float(level))\n        except (TypeError, ValueError):\n            level = 0\n        if level == int(self.active_level):\n            return\n        self.active_level = level\n        # Composition tiles from different levels share x/y names, so both the\n        # rendered-chunk and decoded-tile caches must be level-aware/invalidated.\n        self.chunk_cache.clear()\n        self._composition_tile_cache.clear()\n        if self._composition_zip is not None:\n            self._composition_zip.close()\n        self._composition_zip = None\n        self._composition_zip_path = ""\n\n    def _composition_archive_path(self) -> Path | None:\n        archive_key = "underground_composition_archive" if self._uses_underground_composition() else "baked_composition_archive"\n        raw = str(self.map_config.get(archive_key, "")).strip()\n        if not raw:\n            return None\n        requested = Path(raw)\n        candidates = [requested] if requested.is_absolute() else [Path(__file__).resolve().parent / requested]\n        if not requested.is_absolute():\n            parts = requested.parts[1:] if requested.parts and requested.parts[0] == "assets" else requested.parts\n            candidates.append(shared_assets_root().joinpath(*parts))\n        return next((path for path in candidates if path.is_file()), None)\n\n    def _composition_source_settings(self) -> tuple[float, float]:\n        if self._uses_underground_composition():\n            scale = max(0.01, float(self.map_config.get("underground_composition_source_scale", 1.0)))\n            world_y0 = float(self.map_config.get("underground_composition_world_y", 0.0))\n            return scale, world_y0\n        scale = max(0.01, float(self.map_config.get("baked_composition_source_scale", 0.5)))\n        world_y0 = float(self.map_config.get("baked_composition_world_y", 2048.0))\n        return scale, world_y0\n'''
    text, did = replace_once(
        text, old_method, new_method,
        label="environment composition selector",
        marker="def _uses_underground_composition",
    )
    changed |= did

    text, did = replace_once(
        text,
        "        key = (mode, int(tile_x), int(tile_y))\n",
        "        key = (int(self.active_level), mode, int(tile_x), int(tile_y))\n",
        label="composition tile cache level",
        marker="key = (int(self.active_level), mode, int(tile_x), int(tile_y))",
    )
    changed |= did

    text, did = replace_once(
        text,
        "        scale = max(0.01, float(self.map_config.get(\"baked_composition_source_scale\", 0.5)))\n        world_y0 = float(self.map_config.get(\"baked_composition_world_y\", 2048.0))\n",
        "        scale, world_y0 = self._composition_source_settings()\n",
        label="composition scale selector",
        marker="scale, world_y0 = self._composition_source_settings()",
    )
    changed |= did

    text, did = replace_once(
        text,
        "        key = (cx, cy, int(round(self.view_rotation_degrees)) % 360)\n",
        "        key = (cx, cy, int(round(self.view_rotation_degrees)) % 360, int(self.active_level))\n",
        label="rendered chunk cache level",
        marker="int(self.active_level))\n        cached = self.chunk_cache.get(key)",
    )
    changed |= did

    if changed:
        ENV.write_text(text, encoding="utf-8")
    return changed


def patch_client() -> bool:
    text = CLIENT.read_text(encoding="utf-8")
    changed = False

    text, did = replace_once(
        text,
        '''        self.environment.draw_view(self.screen, self.camera())\n        self.draw_hydrant_effects()\n        self.draw_bike_lanes()\n\n        # Traffic signals remain dynamic because their state is synchronized\n''',
        '''        local_world_player = self.players.get(self.local_id or "")\n        active_world_level = int(getattr(local_world_player, "level", 0)) if local_world_player is not None else 0\n        self.environment.set_active_level(active_world_level)\n        self.environment.draw_view(self.screen, self.camera())\n        # Ground street furniture/state must not bleed through the subterranean\n        # composition. Underground static detail is already baked into its tiles.\n        if active_world_level < 0:\n            return\n        self.draw_hydrant_effects()\n        self.draw_bike_lanes()\n\n        # Traffic signals remain dynamic because their state is synchronized\n''',
        label="client draw_world level selection",
        marker="self.environment.set_active_level(active_world_level)",
    )
    changed |= did

    text, did = replace_once(
        text,
        '''                    self.draw_world()\n                    for stain in self.blood_stains.values():\n                        self.draw_blood_stain(stain)\n''',
        '''                    self.draw_world()\n                    local_world_player = self.players.get(self.local_id or "")\n                    active_world_level = int(getattr(local_world_player, "level", 0)) if local_world_player is not None else 0\n                    if active_world_level >= 0:\n                        for stain in self.blood_stains.values():\n                            self.draw_blood_stain(stain)\n''',
        label="client ground-only stains",
        marker="if active_world_level >= 0:\n                        for stain in self.blood_stains.values():",
    )
    changed |= did

    old_drawables = '''                    drawables = []\n                    drawables.extend((self.camera_depth(car.render_x, car.render_y), "car", car) for car in self.vehicles.values())\n                    drawables.extend((self.camera_depth(bike.render_x, bike.render_y), "bike", bike) for bike in self.bicycles.values())\n                    drawables.extend((self.camera_depth(npc.render_x, npc.render_y), "npc", npc) for npc in self.npcs.values())\n                    drawables.extend(\n                        (self.camera_depth(player.render_x, player.render_y), "player", player)\n                        for player in self.players.values() if int(getattr(player, "level", 0)) <= 0\n                    )\n'''
    new_drawables = '''                    drawables = []\n                    if active_world_level >= 0:\n                        # Vehicles/NPC traffic and blood are currently a Ground-only\n                        # system. Negative-level players are hidden from the surface.\n                        drawables.extend((self.camera_depth(car.render_x, car.render_y), "car", car) for car in self.vehicles.values())\n                        drawables.extend((self.camera_depth(bike.render_x, bike.render_y), "bike", bike) for bike in self.bicycles.values())\n                        drawables.extend((self.camera_depth(npc.render_x, npc.render_y), "npc", npc) for npc in self.npcs.values())\n                        drawables.extend(\n                            (self.camera_depth(player.render_x, player.render_y), "player", player)\n                            for player in self.players.values() if int(getattr(player, "level", 0)) == 0\n                        )\n                    else:\n                        # Underground players see only players sharing their exact\n                        # authoritative negative level. No Ground traffic leaks in.\n                        drawables.extend(\n                            (self.camera_depth(player.render_x, player.render_y), "player", player)\n                            for player in self.players.values() if int(getattr(player, "level", 0)) == active_world_level\n                        )\n'''
    text, did = replace_once(
        text, old_drawables, new_drawables,
        label="client dynamic level isolation",
        marker="Underground players see only players sharing their exact",
    )
    changed |= did

    old_elevated = '''                    positive_levels = sorted({\n                        int(float(road.get("level", 0) or 0))\n                        for road in self.map_config.get("roads", []) or []\n                        if int(float(road.get("level", 0) or 0)) > 0\n                    })\n                    for map_level in positive_levels:\n                        self.environment.draw_elevated_overlay(self.screen, self.camera(), map_level)\n                        level_players = [\n                            (self.camera_depth(player.render_x, player.render_y), player)\n                            for player in self.players.values()\n                            if int(getattr(player, "level", 0)) == map_level\n                        ]\n                        for _, player in sorted(level_players, key=lambda row: row[0]):\n                            self.draw_player(player, local=(player.id == self.local_id))\n'''
    new_elevated = '''                    if active_world_level >= 0:\n                        positive_levels = sorted({\n                            int(float(road.get("level", 0) or 0))\n                            for road in self.map_config.get("roads", []) or []\n                            if int(float(road.get("level", 0) or 0)) > 0\n                        })\n                        for map_level in positive_levels:\n                            self.environment.draw_elevated_overlay(self.screen, self.camera(), map_level)\n                            level_players = [\n                                (self.camera_depth(player.render_x, player.render_y), player)\n                                for player in self.players.values()\n                                if int(getattr(player, "level", 0)) == map_level\n                            ]\n                            for _, player in sorted(level_players, key=lambda row: row[0]):\n                                self.draw_player(player, local=(player.id == self.local_id))\n'''
    text, did = replace_once(
        text, old_elevated, new_elevated,
        label="client elevated isolation",
        marker="if active_world_level >= 0:\n                        positive_levels = sorted",
    )
    changed |= did

    text, did = replace_once(
        text,
        '''    def draw_player_nameplates(self) -> None:\n        """Draw names in final screen space so camera rotation never tilts text."""\n        for player in self.players.values():\n            if getattr(player, "interior_id", ""):\n''',
        '''    def draw_player_nameplates(self) -> None:\n        """Draw names in final screen space so camera rotation never tilts text."""\n        local_world_player = self.players.get(self.local_id or "")\n        active_world_level = int(getattr(local_world_player, "level", 0)) if local_world_player is not None else 0\n        for player in self.players.values():\n            player_level = int(getattr(player, "level", 0))\n            if active_world_level < 0 and player_level != active_world_level:\n                continue\n            if active_world_level >= 0 and player_level < 0:\n                continue\n            if getattr(player, "interior_id", ""):\n''',
        label="client nameplate level isolation",
        marker="player_level = int(getattr(player, \"level\", 0))",
    )
    changed |= did

    text, did = replace_once(
        text,
        '''    def draw_job_location_labels(self) -> None:\n        """Draw supplier/buyer labels in final screen space so they stay horizontal."""\n        w, h = self.screen.get_size()\n''',
        '''    def draw_job_location_labels(self) -> None:\n        """Draw supplier/buyer labels in final screen space so they stay horizontal."""\n        local_world_player = self.players.get(self.local_id or "")\n        if local_world_player is not None and int(getattr(local_world_player, "level", 0)) < 0:\n            return\n        w, h = self.screen.get_size()\n''',
        label="client job-label underground isolation",
        marker="local_world_player is not None and int(getattr(local_world_player, \"level\", 0)) < 0",
    )
    changed |= did

    if changed:
        CLIENT.write_text(text, encoding="utf-8")
    return changed


def patch_map() -> bool:
    text = MAP.read_text(encoding="utf-8-sig")
    changed = False
    text, did = replace_once(
        text,
        "underground_runtime_wired,false,bool",
        "underground_runtime_wired,true,bool",
        label="map Underground runtime flag",
        marker="underground_runtime_wired,true,bool",
    )
    changed |= did
    if "map_build_id,open_night_v1_0_ground_overlay_underground_runtime_v1,str" not in text:
        old = "map_build_id,open_night_v1_0_ground_overlay_underground_semantics_v1,str"
        if old not in text:
            raise RuntimeError("map build id anchor missing")
        text = text.replace(old, "map_build_id,open_night_v1_0_ground_overlay_underground_runtime_v1,str", 1)
        changed = True
    if changed:
        MAP.write_text(text, encoding="utf-8-sig")
    return changed


def patch_underground_workflow() -> bool:
    text = UNDERGROUND_WORKFLOW.read_text(encoding="utf-8")
    changed = False
    text, did = replace_once(
        text,
        "          assert cfg['underground_runtime_wired'].lower() == 'false'\n",
        "          assert cfg['underground_runtime_wired'].lower() == 'true'\n",
        label="Underground CI runtime flag",
        marker="assert cfg['underground_runtime_wired'].lower() == 'true'",
    )
    changed |= did
    text, did = replace_once(
        text,
        "          print('V100_UNDERGROUND_ART_CONTRACT_OK level=-1 archive=192 player_preview=1280x720 runtime_wired=false')\n",
        "          print('V100_UNDERGROUND_ART_CONTRACT_OK level=-1 archive=192 player_preview=1280x720 runtime_wired=true')\n",
        label="Underground CI status text",
        marker="runtime_wired=true')",
    )
    changed |= did
    if changed:
        UNDERGROUND_WORKFLOW.write_text(text, encoding="utf-8")
    return changed


def main():
    changed = {
        "environment_art.py": patch_environment(),
        "client.py": patch_client(),
        "map.csv": patch_map(),
        "v100-underground-art.yml": patch_underground_workflow(),
    }
    touched = [name for name, value in changed.items() if value]
    print("V100_UNDERGROUND_RUNTIME_PATCH_OK changed=" + (",".join(touched) if touched else "none"))


if __name__ == "__main__":
    main()
