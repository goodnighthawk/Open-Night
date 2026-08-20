#!/usr/bin/env python3
"""Apply v1.0 world-registered First Floor runtime integration.

The patch keeps ``interior_id`` as the multiplayer namespace so building floors
never collide with the road/bridge ``player.level`` namespace. It promotes
``interior_x/y`` from detached 10x8 cell indices to authoritative world-space
floats inside each interior's bound building footprint.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOADER = ROOT / "mapfiles/loader.py"
COMMON = ROOT / "common.py"
SERVER = ROOT / "server.py"
CLIENT = ROOT / "client.py"
MAP = ROOT / "mapfiles/data/map_001_gwb_corridor/map.csv"


def replace_once(text: str, old: str, new: str, label: str, marker: str | None = None) -> tuple[str,bool]:
    if marker and marker in text:
        return text, False
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one anchor, found {count}")
    return text.replace(old,new,1), True


def patch_loader() -> bool:
    text = LOADER.read_text(encoding="utf-8")
    old = '''        interiors.append({
            "id": str(row.get("interior_id", "interior")),
            "entry": [float(row.get("entry_x", 0)), float(row.get("entry_y", 0))],
            "kind": str(row.get("kind", "generic")),
            "name": str(row.get("name", row.get("interior_id", "Interior"))),
        })
'''
    new = '''        interiors.append({
            "id": str(row.get("interior_id", "interior")),
            "entry": [float(row.get("entry_x", 0)), float(row.get("entry_y", 0))],
            "kind": str(row.get("kind", "generic")),
            "name": str(row.get("name", row.get("interior_id", "Interior"))),
            "building_id": str(row.get("building_id", "")),
            "door_hint": str(row.get("door_hint", "")),
        })
'''
    text,changed=replace_once(text,old,new,"loader interior building binding",'"building_id": str(row.get("building_id", ""))')
    if changed: LOADER.write_text(text,encoding="utf-8")
    return changed


def patch_common() -> bool:
    text=COMMON.read_text(encoding="utf-8")
    changed=False
    text,did=replace_once(
        text,
        '''    interior_id: str = ""
    interior_x: int = 0
    interior_y: int = 0
    interior_aim: float = 0.0
''',
        '''    interior_id: str = ""
    # v1.0 First Floor positions are world-space coordinates inside the bound
    # building footprint, not detached room-grid indices.
    interior_x: float = 0.0
    interior_y: float = 0.0
    interior_aim: float = 0.0
''',
        "PlayerState interior coordinate types",
        marker="interior_x: float = 0.0",
    ); changed|=did
    text,did=replace_once(
        text,
        '''            "interior_id": self.interior_id,
            "interior_x": int(self.interior_x),
            "interior_y": int(self.interior_y),
            "interior_aim": round(float(self.interior_aim), 4),
''',
        '''            "interior_id": self.interior_id,
            "interior_x": round(float(self.interior_x), 2),
            "interior_y": round(float(self.interior_y), 2),
            "interior_aim": round(float(self.interior_aim), 4),
''',
        "PlayerState public interior floats",
        marker='"interior_x": round(float(self.interior_x), 2)',
    ); changed|=did
    if changed: COMMON.write_text(text,encoding="utf-8")
    return changed


def patch_server() -> bool:
    text=SERVER.read_text(encoding="utf-8")
    changed=False
    text,did=replace_once(
        text,
        'from interior_layout import START_TILE as INTERIOR_START_TILE, interior_step\n',
        'from interior_layout import INTERIOR_STEP, interior_move_world, interior_start_world\n',
        "server interior imports",
        marker="interior_move_world, interior_start_world",
    ); changed|=did
    text,did=replace_once(
        text,
        '''        "x": int(player.interior_x),
        "y": int(player.interior_y),
''',
        '''        "x": round(float(player.interior_x), 2),
        "y": round(float(player.interior_y), 2),
''',
        "server interior payload floats",
        marker='"x": round(float(player.interior_x), 2)',
    ); changed|=did
    text,did=replace_once(
        text,
        '''        player.interior_id = str(info.get("id", ""))
        player.interior_x, player.interior_y = INTERIOR_START_TILE
        player.interior_aim = -math.pi / 2.0
''',
        '''        player.interior_id = str(info.get("id", ""))
        player.interior_x, player.interior_y = interior_start_world(ACTIVE_MAP, player.interior_id)
        player.interior_aim = -math.pi / 2.0
''',
        "server world-registered interior spawn",
        marker="interior_start_world(ACTIVE_MAP, player.interior_id)",
    ); changed|=did
    text,did=replace_once(
        text,
        '''        try:
            dx, dy = int(message.get("dx", 0)), int(message.get("dy", 0))
        except (TypeError, ValueError):
            return
        nx, ny, aim = interior_step(
            player.interior_id, player.interior_x, player.interior_y, dx, dy
        )
        player.interior_x, player.interior_y, player.interior_aim = nx, ny, aim
''',
        '''        try:
            dx, dy = float(message.get("dx", 0.0)), float(message.get("dy", 0.0))
        except (TypeError, ValueError):
            return
        nx, ny, aim = interior_move_world(
            ACTIVE_MAP, player.interior_id,
            player.interior_x, player.interior_y,
            dx, dy, step=INTERIOR_STEP,
        )
        player.interior_x, player.interior_y, player.interior_aim = nx, ny, aim
''',
        "server continuous interior movement",
        marker="nx, ny, aim = interior_move_world(",
    ); changed|=did
    text,did=replace_once(
        text,
        '        player.interior_x = player.interior_y = 0\n',
        '        player.interior_x = player.interior_y = 0.0\n',
        "server interior reset floats",
        marker="player.interior_x = player.interior_y = 0.0",
    ); changed|=did
    if changed: SERVER.write_text(text,encoding="utf-8")
    return changed


def patch_client() -> bool:
    text=CLIENT.read_text(encoding="utf-8")
    changed=False
    text,did=replace_once(
        text,
        '        self.interior = IsometricInterior()\n',
        '        self.interior = IsometricInterior(self.map_config)\n',
        "client registered interior init",
        marker="IsometricInterior(self.map_config)",
    ); changed|=did
    text,did=replace_once(
        text,
        '''                    self.environment.set_map(self.map_config)
                    self._world_map_cache = None
''',
        '''                    self.environment.set_map(self.map_config)
                    self.interior.set_map(self.map_config)
                    self._world_map_cache = None
''',
        "client map refresh interior binding",
        marker="self.interior.set_map(self.map_config)",
    ); changed|=did
    # Remote player parse occurs in constructor and update.
    old='''        self.interior_x = int(data.get("interior_x", 0) or 0)
        self.interior_y = int(data.get("interior_y", 0) or 0)
'''
    new='''        self.interior_x = float(data.get("interior_x", 0.0) or 0.0)
        self.interior_y = float(data.get("interior_y", 0.0) or 0.0)
'''
    if old in text:
        text=text.replace(old,new,1); changed=True
    elif 'self.interior_x = float(data.get("interior_x", 0.0) or 0.0)' not in text:
        raise RuntimeError("client initial interior float anchor missing")
    old='''        self.interior_x = int(data.get("interior_x", getattr(self, "interior_x", 0)) or 0)
        self.interior_y = int(data.get("interior_y", getattr(self, "interior_y", 0)) or 0)
'''
    new='''        self.interior_x = float(data.get("interior_x", getattr(self, "interior_x", 0.0)) or 0.0)
        self.interior_y = float(data.get("interior_y", getattr(self, "interior_y", 0.0)) or 0.0)
'''
    if old in text:
        text=text.replace(old,new,1); changed=True
    elif 'self.interior_x = float(data.get("interior_x", getattr(self, "interior_x", 0.0)) or 0.0)' not in text:
        raise RuntimeError("client update interior float anchor missing")
    text,did=replace_once(
        text,
        '''                    int(message.get("x", 0) or 0),
                    int(message.get("y", 0) or 0),
''',
        '''                    float(message.get("x", 0.0) or 0.0),
                    float(message.get("y", 0.0) or 0.0),
''',
        "client interior_state message floats",
        marker='float(message.get("x", 0.0) or 0.0)',
    ); changed|=did
    text,did=replace_once(
        text,
        '''        self, active: bool, interior_id: str, x: int, y: int, aim: float,
        title: str = "",
    ) -> None:
        """Mirror the server-authoritative room and tile into the local view."""
''',
        '''        self, active: bool, interior_id: str, x: float, y: float, aim: float,
        title: str = "",
    ) -> None:
        """Mirror server-authoritative world X/Y into the First Floor view."""
''',
        "client interior sync contract",
        marker="Mirror server-authoritative world X/Y",
    ); changed|=did
    text,did=replace_once(
        text,
        '''        self.last_send = now
        x, y = self.input_vector()
        keys = pygame.key.get_pressed()
''',
        '''        self.last_send = now
        if self.interior.active:
            interior_blocked = self.pause_menu_open or self.issue_report_open or self.inventory_open or self.map_open or self.chat_active
            ix, iy = movement_vector(blocked=interior_blocked)
            self.network.send({"type": "interior_move", "dx": ix, "dy": iy})
            return
        x, y = self.input_vector()
        keys = pygame.key.get_pressed()
''',
        "client continuous First Floor input",
        marker='self.network.send({"type": "interior_move", "dx": ix, "dy": iy})',
    ); changed|=did
    text,did=replace_once(
        text,
        '''                        if self.interior.active:
                            was_active = self.interior.active
                            before_x, before_y = self.interior.player_x, self.interior.player_y
                            self.interior.handle_key(event.key)
                            if was_active and not self.interior.active:
                                self.network.send({"type": "interior_exit"})
                            elif self.interior.active and (self.interior.player_x, self.interior.player_y) != (before_x, before_y):
                                self.network.send({
                                    "type": "interior_move",
                                    "dx": self.interior.player_x - before_x,
                                    "dy": self.interior.player_y - before_y,
                                })
                            continue
''',
        '''                        if self.interior.active:
                            was_active = self.interior.active
                            self.interior.handle_key(event.key)
                            if was_active and not self.interior.active:
                                self.network.send({"type": "interior_exit"})
                            # Movement is sampled continuously in send_input();
                            # keydown events no longer mutate a detached room grid.
                            continue
''',
        "client remove discrete interior stepping",
        marker="Movement is sampled continuously in send_input()",
    ); changed|=did
    if changed: CLIENT.write_text(text,encoding="utf-8")
    return changed


def patch_map() -> bool:
    text=MAP.read_text(encoding="utf-8-sig")
    changed=False
    additions='''first_floor_runtime_mode,world_registered_interiors_v1,str
first_floor_runtime_wired,true,bool
first_floor_building_namespace,interior_id,str
'''
    if "first_floor_runtime_mode,world_registered_interiors_v1,str" not in text:
        anchor="underground_runtime_checkpoint,audited_switching_v1,str\n"
        if anchor not in text: raise RuntimeError("map first-floor anchor missing")
        text=text.replace(anchor,anchor+additions,1); changed=True
    if "map_build_id,open_night_v1_0_ground_underground_first_floor_runtime_v1,str" not in text:
        old="map_build_id,open_night_v1_0_ground_overlay_underground_runtime_v1,str"
        if old not in text: raise RuntimeError("map build id anchor missing")
        text=text.replace(old,"map_build_id,open_night_v1_0_ground_underground_first_floor_runtime_v1,str",1); changed=True
    if changed: MAP.write_text(text,encoding="utf-8-sig")
    return changed


def main() -> None:
    changed={
        "mapfiles/loader.py":patch_loader(),
        "common.py":patch_common(),
        "server.py":patch_server(),
        "client.py":patch_client(),
        "map.csv":patch_map(),
    }
    print("V100_FIRST_FLOOR_RUNTIME_PATCH_OK changed="+",".join(k for k,v in changed.items() if v))


if __name__ == "__main__":
    main()
