from __future__ import annotations

import argparse
import base64
import asyncio
import csv
import json
import math
import queue
import random
import re
import socket
import sys
import threading
import time
import traceback
from pathlib import Path

import pygame

# The desktop client uses the Python websockets package. Pygbag runs in a
# browser/WASM runtime where that package/background-thread path is not the
# right transport, so browser builds use window.WebSocket instead.
if sys.platform != "emscripten":
    from websockets.asyncio.client import connect
    from websockets.exceptions import ConnectionClosed
else:
    connect = None

    class ConnectionClosed(Exception):
        pass

from common import (
    BUY_PRICE,
    CHARACTER_DEFAULT,
    TRAFFIC_CAR_COLORS,
    TRAFFIC_CAR_LENGTH,
    TRAFFIC_CAR_WIDTH,
    CUSTOMER_POS,
    DEFAULT_MAP_ID,
    INTERACT_DISTANCE,
    INVENTORY_COLS,
    INVENTORY_MAX_WEIGHT_KG,
    INVENTORY_ROWS,
    INVENTORY_SLOT_COUNT,
    ITEM_DEFS,
    PLAYER_RADIUS,
    SELL_PRICE,
    SUPPLIER_POS,
    empty_inventory,
    get_map,
    inventory_count,
    inventory_weight,
    normalize_character,
    normalize_inventory,
    world_to_chunk,
)
from art_style import load_art_style, StyleWatcher, set_art_style_value
from character_art import draw_character, reload_character_style
from character_catalog import custom_options as character_custom_options, preset_options as character_preset_options, profile_parts as character_profile_parts, display_label as character_display_label, catalog as character_catalog
from vehicle_art import draw_car, reload_vehicle_style
from environment_art import EnvironmentRenderer
from interior_art import IsometricInterior
from bicycle_art import draw_bicycle
from gameplay.settings import load_settings, set_setting_value, CONFIG_PATH as GAME_SETTINGS_PATH
from gameplay.camera_controller import LookAheadCamera
from gameplay.input_controller import movement_vector
from gameplay.issue_reporter import save_issue_report
from portable_paths import describe as shared_data_description
from portable_map_runtime import cached_map_hashes, install_transfer_bundle, load_cached_map
from mapfiles.grid import chunk_label
from server_directory import choose_browser_server_uri, load_public_servers, probe_public_servers

SCREEN_W = 1280
SCREEN_H = 720
FPS = 120
NETWORK_SEND_RATE = 30
DISCOVERY_MAGIC = "PYMMO_DISCOVER_V1"
DISCOVERY_PORT_START = 8765
DISCOVERY_PORT_END = 8795
DISCOVERY_INTERVAL = 1.5
DISCOVERY_STALE_AFTER = 12.0
PUBLIC_SERVER_PROBE_INTERVAL = 5.0
FRIENDS_PATH = Path(__file__).resolve().parent / "config" / "friends.csv"

ROAD_COLOR = (38, 41, 41)
ROAD_GRAIN = (47, 50, 49)
LANE_COLOR = (164, 158, 130)
CURB_COLOR = (112, 112, 105)
SIDEWALK_COLOR = (82, 84, 80)
BUILDING_COLOR = (119, 108, 93)
BUILDING_EDGE = (61, 58, 53)
ROOF_PALETTE = [(116, 105, 91), (102, 105, 101), (125, 96, 82), (91, 100, 93)]
LOCAL_COLOR = (245, 218, 88)
REMOTE_COLOR = (105, 190, 245)
SUPPLIER_COLOR = (108, 210, 135)
CUSTOMER_COLOR = (224, 113, 113)
TEXT_COLOR = (242, 242, 238)
MUTED_TEXT = (155, 158, 161)
SHADOW = (15, 15, 15)
INV_BG = (18, 20, 21)
INV_PANEL = (26, 28, 29)
INV_SLOT = (35, 37, 38)
INV_SLOT_EDGE = (70, 73, 74)
INV_SELECTED = (233, 205, 94)


def apply_client_art_style() -> dict:
    global TEXT_COLOR, MUTED_TEXT, INV_BG, INV_PANEL, INV_SELECTED
    global LOCAL_COLOR, REMOTE_COLOR, SUPPLIER_COLOR, CUSTOMER_COLOR
    style = load_art_style()
    ui = style.get("ui", {})
    TEXT_COLOR = tuple(ui.get("text", TEXT_COLOR))
    MUTED_TEXT = tuple(ui.get("muted", MUTED_TEXT))
    INV_BG = tuple(ui.get("panel", INV_BG))
    INV_PANEL = tuple(ui.get("panel_2", INV_PANEL))
    INV_SELECTED = tuple(ui.get("accent", INV_SELECTED))
    LOCAL_COLOR = tuple(ui.get("local", LOCAL_COLOR))
    REMOTE_COLOR = tuple(ui.get("remote", REMOTE_COLOR))
    SUPPLIER_COLOR = tuple(ui.get("supplier", SUPPLIER_COLOR))
    CUSTOMER_COLOR = tuple(ui.get("customer", CUSTOMER_COLOR))
    return style


apply_client_art_style()


def random_default_phone() -> str:
    """Return a synthetic 10-digit prototype account number.

    The 555 prefix makes the pre-filled value obviously test-oriented while
    leaving seven random digits, so separate client launches normally receive
    different account identifiers. Users can replace it before connecting.
    """
    return f"555{random.randint(0, 9_999_999):07d}"


class DiscoveryService:
    def __init__(self, port_start: int = DISCOVERY_PORT_START, port_end: int = DISCOVERY_PORT_END):
        self.port_start = port_start
        self.port_end = port_end
        self._servers: dict[str, dict] = {}
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._refresh = threading.Event()
        self._last_tcp_probe = 0.0
        self._last_public_probe = 0.0
        self._public_servers = load_public_servers()
        self._public_status = "checking" if self._public_servers else "not configured"
        self._thread = threading.Thread(target=self._thread_main, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._refresh.set()

    def refresh(self) -> None:
        self._last_public_probe = 0.0
        self._refresh.set()

    def public_status(self) -> str:
        with self._lock:
            return self._public_status

    def snapshot(self) -> list[dict]:
        now = time.monotonic()
        with self._lock:
            stale = [uri for uri, item in self._servers.items() if now - item["last_seen"] > DISCOVERY_STALE_AFTER]
            for uri in stale:
                self._servers.pop(uri, None)
            return sorted(
                (dict(item) for item in self._servers.values()),
                key=lambda item: (
                    0 if item.get("scope") == "INTERNET" else 1,
                    item.get("name", "").lower(),
                    item.get("uri", ""),
                ),
            )

    def _thread_main(self) -> None:
        while not self._stop.is_set():
            self._scan_once()
            self._refresh.wait(DISCOVERY_INTERVAL)
            self._refresh.clear()

    def _scan_once(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.settimeout(0.06)
            sock.bind(("", 0))
            payload = DISCOVERY_MAGIC.encode("utf-8")
            hosts = {"127.0.0.1", "255.255.255.255"}
            # Directed /24 broadcasts work on many Windows networks where the
            # limited broadcast address is filtered.  This is deliberately only
            # a discovery hint; the response source address remains authoritative.
            try:
                for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
                    ip = info[4][0]
                    parts = ip.split(".")
                    if len(parts) == 4 and ip != "127.0.0.1":
                        hosts.add(".".join(parts[:3] + ["255"]))
            except OSError:
                pass
            for port in range(self.port_start, self.port_end + 1):
                for host in hosts:
                    try:
                        sock.sendto(payload, (host, port))
                    except OSError:
                        pass
            deadline = time.monotonic() + 0.45
            while time.monotonic() < deadline and not self._stop.is_set():
                try:
                    raw, addr = sock.recvfrom(8192)
                except socket.timeout:
                    continue
                except OSError:
                    break
                try:
                    data = json.loads(raw.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    continue
                if data.get("protocol") != DISCOVERY_MAGIC:
                    continue
                try:
                    port = int(data["port"])
                except (KeyError, TypeError, ValueError):
                    continue
                host = addr[0]
                uri = f"ws://{host}:{port}"
                item = {
                    "uri": uri,
                    "name": str(data.get("name", "Python MMO Server")),
                    "players": int(data.get("players", 0)),
                    "max_players": int(data.get("max_players", 0)),
                    "version": str(data.get("version", "dev")),
                    "map_id": str(data.get("map_id", DEFAULT_MAP_ID)),
                    "map_name": str(data.get("map_name", "Unknown map")),
                    "host": host,
                    "port": port,
                    "scope": "LAN",
                    "last_seen": time.monotonic(),
                }
                with self._lock:
                    self._servers[uri] = item

            # Robust same-machine fallback. UDP discovery can be blocked by the
            # Windows firewall even while the WebSocket server is reachable.
            # Probe the small configured port range over WebSockets at a low rate.
            now = time.monotonic()
            if now - self._last_tcp_probe > 4.0:
                self._last_tcp_probe = now
                try:
                    results = asyncio.run(self._probe_local_servers())
                except Exception:
                    results = []
                for item in results:
                    with self._lock:
                        self._servers[item["uri"]] = item

            # Configured public endpoints are verified with the real game
            # protocol. They appear in the launcher only while reachable.
            now = time.monotonic()
            if self._public_servers and now - self._last_public_probe > PUBLIC_SERVER_PROBE_INTERVAL:
                self._last_public_probe = now
                try:
                    public_results = asyncio.run(probe_public_servers(self._public_servers))
                except Exception:
                    public_results = []
                reachable = {item["uri"] for item in public_results}
                configured = {item["uri"] for item in self._public_servers}
                with self._lock:
                    for uri in configured - reachable:
                        self._servers.pop(uri, None)
                    for item in public_results:
                        self._servers[item["uri"]] = item
                    self._public_status = "online" if public_results else "offline"
        finally:
            sock.close()

    async def _probe_one_local(self, port: int) -> dict | None:
        uri = f"ws://127.0.0.1:{int(port)}"
        try:
            async with connect(uri, open_timeout=0.18, close_timeout=0.05, ping_interval=None) as ws:
                await ws.send(json.dumps({"type": "probe"}, separators=(",", ":")))
                raw = await asyncio.wait_for(ws.recv(), timeout=0.20)
            data = json.loads(raw)
            if data.get("type") != "server_info" or data.get("protocol") != DISCOVERY_MAGIC:
                return None
            return {
                "uri": uri,
                "name": str(data.get("name", "Local Python MMO Server")),
                "players": int(data.get("players", 0)),
                "max_players": int(data.get("max_players", 0)),
                "version": str(data.get("version", "dev")),
                "map_id": str(data.get("map_id", DEFAULT_MAP_ID)),
                "map_name": str(data.get("map_name", "Unknown map")),
                "host": "127.0.0.1",
                "port": int(port),
                "scope": "LOCAL",
                "last_seen": time.monotonic(),
            }
        except Exception:
            return None

    async def _probe_local_servers(self) -> list[dict]:
        tasks = [self._probe_one_local(port) for port in range(self.port_start, self.port_end + 1)]
        values = await asyncio.gather(*tasks, return_exceptions=False)
        return [item for item in values if item is not None]


class TextField:
    def __init__(self, rect: pygame.Rect, text: str = "", placeholder: str = "", max_length: int = 64):
        self.rect = rect
        self.text = text
        self.placeholder = placeholder
        self.max_length = max_length
        self.active = False

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self.active = self.rect.collidepoint(event.pos)
        elif event.type == pygame.KEYDOWN and self.active:
            if event.key == pygame.K_BACKSPACE:
                self.text = self.text[:-1]
            elif event.key not in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_TAB, pygame.K_ESCAPE):
                if event.unicode and event.unicode.isprintable() and len(self.text) < self.max_length:
                    self.text += event.unicode

    def draw(self, surface: pygame.Surface, font: pygame.font.Font) -> None:
        border = (235, 210, 92) if self.active else (105, 108, 112)
        pygame.draw.rect(surface, (25, 27, 29), self.rect, border_radius=6)
        pygame.draw.rect(surface, border, self.rect, width=2, border_radius=6)
        shown = self.text or self.placeholder
        color = TEXT_COLOR if self.text else (125, 128, 132)
        text_surface = font.render(shown, True, color)
        clip = self.rect.inflate(-18, -8)
        old_clip = surface.get_clip()
        surface.set_clip(clip)
        surface.blit(text_surface, (self.rect.x + 10, self.rect.centery - text_surface.get_height() // 2))
        surface.set_clip(old_clip)


class Launcher:
    def __init__(self, initial_name: str | None = None, initial_phone: str | None = None):
        pygame.init()
        pygame.display.set_caption("Python MMO - Launcher")
        self.screen = pygame.display.set_mode((980, 760), pygame.RESIZABLE)
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("consolas", 19)
        self.small = pygame.font.SysFont("consolas", 15)
        self.title_font = pygame.font.SysFont("consolas", 36, bold=True)
        self.modal_title = pygame.font.SysFont("consolas", 28, bold=True)
        self.phone_field = TextField(
            pygame.Rect(52, 126, 420, 42),
            initial_phone or random_default_phone(),
            "+1 555 123 4567",
            24,
        )
        self.name_field = TextField(pygame.Rect(500, 126, 380, 42), initial_name or f"Player{random.randint(100, 999)}", "Display name", 18)
        self.manual_field = TextField(pygame.Rect(52, 670, 570, 42), "", "ws://192.168.1.50:8765")
        self.selected_uri: str | None = None
        self.message = "Checking the Open Night internet server and your LAN..."
        self.discovery = DiscoveryService()
        self.discovery.start()
        self.last_click_time = 0.0
        self.last_click_uri: str | None = None
        self.customizing = False
        self.appearance = normalize_character(CHARACTER_DEFAULT)
        self.appearance_changed = False
        # v1.2 approved dual-camera paper-doll pack. Only parts registered in
        # both top-down and isometric modes are exposed in the launcher.
        options = character_custom_options()
        self._custom_rows = [
            ("Preset", "profile", character_preset_options()),
            ("Head", "head", options.get("head", [])),
            ("Top", "top", options.get("top", [])),
            ("Bottom", "bottom", options.get("bottom", [])),
            ("Footwear", "footwear", options.get("footwear", [])),
            ("Accessory", "accessory", options.get("accessory", [])),
        ]

    @staticmethod
    def _button(surface: pygame.Surface, rect: pygame.Rect, text: str, font: pygame.font.Font, enabled: bool = True) -> None:
        mouse = pygame.mouse.get_pos()
        hovered = rect.collidepoint(mouse) and enabled
        fill = (73, 77, 80) if hovered else ((54, 57, 60) if enabled else (37, 39, 41))
        edge = (205, 180, 75) if hovered else (105, 108, 112)
        pygame.draw.rect(surface, fill, rect, border_radius=6)
        pygame.draw.rect(surface, edge, rect, width=2, border_radius=6)
        label = font.render(text, True, TEXT_COLOR if enabled else (105, 108, 110))
        surface.blit(label, label.get_rect(center=rect.center))

    def _credentials(self) -> tuple[str, str] | None:
        digits = re.sub(r"\D", "", self.phone_field.text)
        if not 7 <= len(digits) <= 15:
            self.message = "Enter a valid phone number (7-15 digits)."
            return None
        if not self.name_field.text.strip():
            self.message = "Enter a display name."
            return None
        return self.phone_field.text.strip(), self.name_field.text.strip()

    def _result(self, uri: str) -> tuple[str, str, str, dict, bool] | None:
        creds = self._credentials()
        if creds is None:
            return None
        phone, name = creds
        return uri, phone, name, normalize_character(self.appearance), self.appearance_changed

    def _connect_selected(self, servers: list[dict]) -> tuple[str, str, str, dict, bool] | None:
        selected = next((s for s in servers if s["uri"] == self.selected_uri), None)
        if selected is None:
            self.message = "Select a discovered server first."
            return None
        if selected.get("max_players", 0) and selected.get("players", 0) >= selected["max_players"]:
            self.message = "That server is full."
            return None
        return self._result(selected["uri"])

    def _connect_manual(self) -> tuple[str, str, str, dict, bool] | None:
        uri = self.manual_field.text.strip()
        if not uri:
            self.message = "Enter a server address."
            return None
        if not uri.startswith(("ws://", "wss://")):
            uri = "ws://" + uri
        return self._result(uri)

    def _character_label(self, key: str) -> str:
        value = str(self.appearance.get(key, "none"))
        if key == "profile":
            if value == "custom":
                return "Custom mix"
            return character_catalog()["profile_names"].get(value, character_display_label(value))
        return character_display_label(value)

    def _cycle_character_choice(self, key: str, choices: list[str], delta: int) -> None:
        if not choices:
            return
        current = str(self.appearance.get(key, choices[0]))
        try:
            index = choices.index(current)
        except ValueError:
            index = 0
        selected = choices[(index + int(delta)) % len(choices)]
        if key == "profile":
            parts = character_profile_parts(selected, "topdown")
            self.appearance.update(parts)
            self.appearance["profile"] = selected
        else:
            self.appearance[key] = selected
            self.appearance["profile"] = "custom"
        self.appearance = normalize_character(self.appearance)
        self.appearance_changed = True

    def _character_modal(self, event: pygame.event.Event | None = None) -> bool:
        w, h = self.screen.get_size()
        panel = pygame.Rect(max(20, (w - 900) // 2), max(20, (h - 700) // 2), min(900, w - 40), min(700, h - 40))
        done = pygame.Rect(panel.right - 164, panel.bottom - 62, 128, 38)
        reset = pygame.Rect(panel.x + 36, panel.bottom - 62, 128, 38)
        row_buttons: list[tuple[str, pygame.Rect, pygame.Rect, list[str]]] = []
        row_y = panel.y + 135
        for label, key, choices in self._custom_rows:
            left = pygame.Rect(panel.x + 488, row_y, 40, 34)
            right = pygame.Rect(panel.right - 70, row_y, 40, 34)
            row_buttons.append((key, left, right, choices))
            row_y += 54

        if event is not None:
            if event.type == pygame.KEYDOWN and event.key in (pygame.K_ESCAPE, pygame.K_RETURN, pygame.K_KP_ENTER):
                self.customizing = False
                return True
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if done.collidepoint(event.pos):
                    self.customizing = False
                    return True
                if reset.collidepoint(event.pos):
                    self.appearance = normalize_character(CHARACTER_DEFAULT)
                    self.appearance_changed = True
                    return True
                for key, left, right, choices in row_buttons:
                    if left.collidepoint(event.pos):
                        self._cycle_character_choice(key, choices, -1)
                        return True
                    if right.collidepoint(event.pos):
                        self._cycle_character_choice(key, choices, +1)
                        return True
            return False

        shade = pygame.Surface((w, h), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 185))
        self.screen.blit(shade, (0, 0))
        pygame.draw.rect(self.screen, (24, 26, 28), panel, border_radius=10)
        pygame.draw.rect(self.screen, (105, 108, 112), panel, width=2, border_radius=10)
        self.screen.blit(self.modal_title.render("CHARACTER", True, TEXT_COLOR), (panel.x + 36, panel.y + 28))
        self.screen.blit(self.small.render("Approved dual-camera character pack — parts are shared by players and NPCs", True, MUTED_TEXT), (panel.x + 38, panel.y + 68))

        preview = pygame.Rect(panel.x + 30, panel.y + 108, 330, 405)
        pygame.draw.rect(self.screen, (17, 18, 20), preview, border_radius=8)
        pygame.draw.rect(self.screen, (62, 65, 68), preview, width=2, border_radius=8)
        # Show both registered camera modes using the same saved paper-doll parts.
        angle = (time.monotonic() * 0.55) % (math.pi * 2)
        left_center = (preview.x + 88, preview.y + 205)
        right_center = (preview.x + 244, preview.y + 205)
        draw_character(self.screen, left_center, angle, self.appearance, scale=3, local_ring=(85, 78, 45), moving=True, anim_time=time.monotonic(), mode="topdown")
        draw_character(self.screen, right_center, angle, self.appearance, scale=3, moving=True, anim_time=time.monotonic(), mode="isometric")
        self.screen.blit(self.small.render("TOP-DOWN", True, MUTED_TEXT), (preview.x + 45, preview.bottom - 42))
        self.screen.blit(self.small.render("ISOMETRIC", True, MUTED_TEXT), (preview.x + 205, preview.bottom - 42))

        row_y = panel.y + 135
        for label, key, choices in self._custom_rows:
            self.screen.blit(self.font.render(label.upper(), True, TEXT_COLOR), (panel.x + 382, row_y + 5))
            left = pygame.Rect(panel.x + 488, row_y, 40, 34)
            right = pygame.Rect(panel.right - 70, row_y, 40, 34)
            self._button(self.screen, left, "<", self.font)
            self._button(self.screen, right, ">", self.font)
            value = self.small.render(self._character_label(key), True, (215, 216, 211))
            value_rect = value.get_rect(center=((left.right + right.left) // 2, row_y + 17))
            self.screen.blit(value, value_rect)
            row_y += 54

        self._button(self.screen, reset, "RESET", self.small)
        self._button(self.screen, done, "DONE", self.small)
        note = "Changes are saved to your account; NPCs use the same approved part catalog."
        self.screen.blit(self.small.render(note, True, (180, 145, 105)), (panel.x + 190, panel.bottom - 51))
        return False

    def run(self) -> tuple[str, str, str, dict, bool] | None:
        try:
            while True:
                self.clock.tick(60)
                w, h = self.screen.get_size()
                servers = self.discovery.snapshot()
                if self.selected_uri not in {s["uri"] for s in servers}:
                    self.selected_uri = servers[0]["uri"] if servers else None

                left_w = max(280, min(420, (w - 126) // 2))
                self.phone_field.rect = pygame.Rect(52, 126, left_w, 42)
                self.name_field.rect = pygame.Rect(74 + left_w, 126, max(240, w - (126 + left_w)), 42)
                customize_rect = pygame.Rect(52, 202, 190, 38)
                list_rect = pygame.Rect(52, 292, max(350, w - 104), max(170, h - 452))
                refresh_rect = pygame.Rect(w - 192, 246, 140, 38)
                join_rect = pygame.Rect(w - 202, h - 72, 150, 42)
                self.manual_field.rect = pygame.Rect(52, h - 72, max(250, w - 430), 42)
                direct_rect = pygame.Rect(self.manual_field.rect.right + 12, h - 72, 150, 42)

                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        return None
                    if self.customizing:
                        self._character_modal(event)
                        continue
                    if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                        return None
                    self.phone_field.handle_event(event)
                    self.name_field.handle_event(event)
                    self.manual_field.handle_event(event)

                    if event.type == pygame.KEYDOWN and event.key == pygame.K_TAB:
                        fields = [self.phone_field, self.name_field, self.manual_field]
                        active = next((i for i, f in enumerate(fields) if f.active), -1)
                        for f in fields:
                            f.active = False
                        fields[(active + 1) % len(fields)].active = True
                    elif event.type == pygame.KEYDOWN and event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                        result = self._connect_manual() if self.manual_field.active and self.manual_field.text.strip() else self._connect_selected(servers)
                        if result:
                            return result
                    elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                        if customize_rect.collidepoint(event.pos):
                            self.customizing = True
                        elif refresh_rect.collidepoint(event.pos):
                            self.discovery.refresh()
                            self.message = "Refreshing internet and LAN server lists..."
                        elif join_rect.collidepoint(event.pos):
                            result = self._connect_selected(servers)
                            if result:
                                return result
                        elif direct_rect.collidepoint(event.pos):
                            result = self._connect_manual()
                            if result:
                                return result
                        elif list_rect.collidepoint(event.pos):
                            row_y = list_rect.y + 12
                            for server in servers:
                                row = pygame.Rect(list_rect.x + 10, row_y, list_rect.width - 20, 58)
                                if row.collidepoint(event.pos):
                                    self.selected_uri = server["uri"]
                                    now = time.monotonic()
                                    if self.last_click_uri == server["uri"] and now - self.last_click_time < 0.4:
                                        result = self._connect_selected(servers)
                                        if result:
                                            return result
                                    self.last_click_uri, self.last_click_time = server["uri"], now
                                    break
                                row_y += 64

                self.screen.fill((18, 20, 22))
                self.screen.blit(self.title_font.render("PYTHON MMO", True, TEXT_COLOR), (52, 36))
                self.screen.blit(self.small.render("persistent account login / character / LAN server browser", True, (160, 163, 166)), (55, 80))
                self.screen.blit(self.small.render("PHONE NUMBER", True, (185, 188, 190)), (52, 105))
                self.screen.blit(self.small.render("DISPLAY NAME", True, (185, 188, 190)), (self.name_field.rect.x, 105))
                self.phone_field.draw(self.screen, self.font)
                self.name_field.draw(self.screen, self.font)
                security = self.small.render("Prototype identity only: phone number is not yet verified by SMS/OTP.", True, (185, 145, 105))
                self.screen.blit(security, (52, 178))
                self._button(self.screen, customize_rect, "CUSTOMIZE CHARACTER", self.small)
                if self.appearance_changed:
                    changed = self.small.render("changes will be saved", True, (166, 211, 170))
                    self.screen.blit(changed, (customize_rect.right + 14, customize_rect.y + 11))

                self.screen.blit(self.font.render(f"AVAILABLE SERVERS ({len(servers)})", True, TEXT_COLOR), (52, 252))
                public_state = self.discovery.public_status().upper()
                public_color = (166, 211, 170) if public_state == "ONLINE" else ((205, 180, 75) if public_state == "CHECKING" else MUTED_TEXT)
                public_label = self.small.render(f"INTERNET: {public_state}", True, public_color)
                self.screen.blit(public_label, (310, 258))
                self._button(self.screen, refresh_rect, "REFRESH", self.small)
                pygame.draw.rect(self.screen, (24, 26, 28), list_rect, border_radius=7)
                pygame.draw.rect(self.screen, (72, 75, 78), list_rect, width=2, border_radius=7)

                if not servers:
                    waiting = "Checking configured internet server..." if public_state == "CHECKING" else "No online internet or LAN servers detected."
                    self.screen.blit(self.font.render(waiting, True, (135, 138, 141)), (list_rect.x + 18, list_rect.y + 20))
                    self.screen.blit(self.small.render("Refresh, start a local server, or use Direct Connect below.", True, (115, 118, 121)), (list_rect.x + 18, list_rect.y + 54))
                else:
                    row_y = list_rect.y + 12
                    max_y = list_rect.bottom - 12
                    for server in servers:
                        if row_y + 58 > max_y:
                            break
                        row = pygame.Rect(list_rect.x + 10, row_y, list_rect.width - 20, 58)
                        selected = server["uri"] == self.selected_uri
                        pygame.draw.rect(self.screen, (61, 58, 43) if selected else (33, 35, 37), row, border_radius=5)
                        if selected:
                            pygame.draw.rect(self.screen, (218, 190, 75), row, width=2, border_radius=5)
                        self.screen.blit(self.font.render(server["name"], True, TEXT_COLOR), (row.x + 12, row.y + 7))
                        max_players = server.get("max_players", 0)
                        occupancy = f'{server.get("players", 0)}/{max_players}' if max_players else str(server.get("players", 0))
                        scope = str(server.get("scope", "LAN"))
                        endpoint = "Railway" if scope == "INTERNET" else f'{server["host"]}:{server["port"]}'
                        details = f'{occupancy} players   {server.get("map_name", "Unknown map")}   {scope} {endpoint}   v{server.get("version", "dev")}'
                        self.screen.blit(self.small.render(details, True, MUTED_TEXT), (row.x + 12, row.y + 34))
                        row_y += 64

                self.screen.blit(self.small.render("DIRECT CONNECT", True, (185, 188, 190)), (52, h - 94))
                self.manual_field.draw(self.screen, self.font)
                self._button(self.screen, direct_rect, "CONNECT", self.small)
                self._button(self.screen, join_rect, "JOIN", self.font, enabled=self.selected_uri is not None)
                self.screen.blit(self.small.render(self.message, True, (159, 162, 165)), (52, h - 118))
                if self.customizing:
                    self._character_modal()
                pygame.display.flip()
        finally:
            self.discovery.stop()


class NetworkClient:
    def __init__(self, uri: str, phone: str, name: str, appearance: dict | None = None, appearance_changed: bool = False):
        self.uri = uri
        self.phone = phone
        self.name = name
        self.appearance = normalize_character(appearance)
        self.appearance_changed = bool(appearance_changed)
        self.incoming: queue.Queue[dict] = queue.Queue()
        self.outgoing: queue.Queue[dict] = queue.Queue(maxsize=128)
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self._thread_main, daemon=True)
        self.connected = False
        self.fatal = False

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()

    def send(self, payload: dict) -> None:
        try:
            self.outgoing.put_nowait(payload)
        except queue.Full:
            try:
                self.outgoing.get_nowait()
            except queue.Empty:
                pass
            try:
                self.outgoing.put_nowait(payload)
            except queue.Full:
                pass

    def _thread_main(self) -> None:
        asyncio.run(self._run())

    async def _sender(self, websocket) -> None:
        while not self.stop_event.is_set():
            try:
                payload = self.outgoing.get_nowait()
            except queue.Empty:
                await asyncio.sleep(0.002)
                continue
            await websocket.send(json.dumps(payload, separators=(",", ":")))

    async def _receiver(self, websocket) -> None:
        async for raw in websocket:
            try:
                message = json.loads(raw)
            except json.JSONDecodeError:
                continue
            self.incoming.put(message)
            if message.get("type") == "login_error":
                self.fatal = True
                self.stop_event.set()
                return

    async def _run(self) -> None:
        while not self.stop_event.is_set():
            try:
                async with connect(self.uri, ping_interval=20, ping_timeout=20) as websocket:
                    hello = {"type": "hello", "name": self.name, "phone": self.phone, "map_cache_hashes": cached_map_hashes()}
                    if self.appearance_changed:
                        hello["appearance"] = self.appearance
                        hello["appearance_changed"] = True
                    await websocket.send(json.dumps(hello))
                    self.connected = True
                    self.incoming.put({"type": "connection", "connected": True})
                    sender = asyncio.create_task(self._sender(websocket))
                    receiver = asyncio.create_task(self._receiver(websocket))
                    done, pending = await asyncio.wait({sender, receiver}, return_when=asyncio.FIRST_COMPLETED)
                    for task in pending:
                        task.cancel()
                    await asyncio.gather(*pending, return_exceptions=True)
                    for task in done:
                        if not task.cancelled():
                            _ = task.exception()
            except (OSError, ConnectionClosed, asyncio.TimeoutError):
                pass
            except Exception as exc:
                self.incoming.put({"type": "notice", "text": f"Network error: {exc}"})
            self.connected = False
            self.incoming.put({"type": "connection", "connected": False})
            if not self.stop_event.is_set() and not self.fatal:
                await asyncio.sleep(1.0)


class BrowserNetworkClient:
    """Pygbag/browser WebSocket adapter with the same small API as NetworkClient.

    Browser builds cannot rely on the desktop background-thread + Python
    ``websockets`` path.  Using the browser's native WebSocket keeps network
    callbacks on the browser event loop and fixes the reconnect loop seen in the
    quick local web test.
    """

    def __init__(self, uri: str, phone: str, name: str, appearance: dict | None = None, appearance_changed: bool = False):
        self.uri = uri
        self.phone = phone
        self.name = name
        self.appearance = normalize_character(appearance)
        self.appearance_changed = bool(appearance_changed)
        self.incoming: queue.Queue[dict] = queue.Queue()
        self.connected = False
        self.fatal = False
        self.websocket = None
        self._callbacks = ()
        self._stopped = False
        self._connecting = False
        self._next_reconnect_at = 0.0

    def start(self) -> None:
        self._stopped = False
        self._connect()

    def _connect(self) -> None:
        if self._stopped or self.fatal or self.connected or self._connecting:
            return
        self._connecting = True
        self._next_reconnect_at = float("inf")
        try:
            import platform
            ctor = platform.window.WebSocket
            try:
                ws = ctor.new(self.uri)
            except Exception:
                ws = ctor(self.uri)
            self.websocket = ws

            def on_open(_event=None):
                self._connecting = False
                if self._stopped:
                    return
                hello = {"type": "hello", "name": self.name, "phone": self.phone, "map_cache_hashes": cached_map_hashes()}
                if self.appearance_changed:
                    hello["appearance"] = self.appearance
                    hello["appearance_changed"] = True
                try:
                    ws.send(json.dumps(hello, separators=(",", ":")))
                    self.connected = True
                    self.incoming.put({"type": "connection", "connected": True})
                except Exception as exc:
                    self.incoming.put({"type": "notice", "text": f"Browser WebSocket send failed: {exc}"})

            def on_message(event):
                try:
                    raw = event.data
                    message = json.loads(str(raw))
                except Exception:
                    return
                self.incoming.put(message)
                if message.get("type") == "login_error":
                    self.fatal = True

            def on_close(_event=None):
                self._connecting = False
                self.connected = False
                self.incoming.put({"type": "connection", "connected": False})
                if not self._stopped and not self.fatal:
                    self._next_reconnect_at = time.monotonic() + 1.0

            def on_error(_event=None):
                self._connecting = False
                if not self.connected:
                    self._next_reconnect_at = time.monotonic() + 1.0
                    self.incoming.put({"type": "notice", "text": f"Browser WebSocket could not connect to {self.uri}"})

            # Keep Python callback objects alive for the lifetime of this socket.
            self._callbacks = (on_open, on_message, on_close, on_error)
            ws.onopen = on_open
            ws.onmessage = on_message
            ws.onclose = on_close
            ws.onerror = on_error
        except Exception as exc:
            self._connecting = False
            self.connected = False
            self._next_reconnect_at = time.monotonic() + 1.0
            self.incoming.put({"type": "connection", "connected": False})
            self.incoming.put({"type": "notice", "text": f"Browser WebSocket setup failed: {exc}"})

    def pump(self) -> None:
        # Reconnect from the normal async game loop rather than a JS timer. This
        # keeps the reconnect lifecycle deterministic and avoids callback/proxy
        # lifetime problems in browser Python runtimes.
        if self._stopped or self.fatal or self.connected or self._connecting:
            return
        if time.monotonic() >= self._next_reconnect_at:
            self._connect()

    def stop(self) -> None:
        self._stopped = True
        self.connected = False
        try:
            if self.websocket is not None:
                self.websocket.close()
        except Exception:
            pass

    def send(self, payload: dict) -> None:
        ws = self.websocket
        if ws is None or not self.connected:
            return
        try:
            # OPEN == 1 in the browser WebSocket API.
            if int(ws.readyState) == 1:
                ws.send(json.dumps(payload, separators=(",", ":")))
        except Exception:
            self.connected = False


class RemotePlayer:
    def __init__(self, data: dict):
        self.id = data["id"]
        self.name = data.get("name", "Player")
        self.render_x = float(data["x"])
        self.render_y = float(data["y"])
        self.target_x = self.render_x
        self.target_y = self.render_y
        self.aim = float(data.get("aim", 0.0))
        self.cash = int(data.get("cash", 0))
        self.packages = int(data.get("packages", 0))
        self.appearance = normalize_character(data.get("appearance"))
        # Vehicle state is optional in older/welcome packets; always initialize it
        # so rendering can safely decide whether the pedestrian sprite is hidden.
        self.in_vehicle = bool(data.get("in_vehicle", False))
        self.vehicle_id = str(data.get("vehicle_id", ""))
        self.vehicle_kind = str(data.get("vehicle_kind", ""))
        self.vehicle_role = str(data.get("vehicle_role", ""))
        self.interior_id = str(data.get("interior_id", ""))
        self.interior_x = int(data.get("interior_x", 0) or 0)
        self.interior_y = int(data.get("interior_y", 0) or 0)
        self.interior_aim = float(data.get("interior_aim", 0.0) or 0.0)
        self.level = int(float(data.get("level", 0) or 0))
        self.moving_until = 0.0
        self.anim_epoch = time.monotonic()
        self.move_heading = float(self.aim)
        self.pose = str(data.get("pose", "idle"))

    def update_from_snapshot(self, data: dict, snap_local: bool = False) -> None:
        self.name = data.get("name", self.name)
        new_x = float(data["x"])
        new_y = float(data["y"])
        motion_dx = new_x - self.target_x
        motion_dy = new_y - self.target_y
        if math.hypot(motion_dx, motion_dy) > 0.35:
            self.moving_until = time.monotonic() + 0.18
            self.move_heading = math.atan2(motion_dy, motion_dx)
        self.target_x = new_x
        self.target_y = new_y
        self.aim = float(data.get("aim", self.aim))
        new_pose = str(data.get("pose", self.pose))
        if new_pose != self.pose:
            self.pose = new_pose
            self.anim_epoch = time.monotonic()
        self.cash = int(data.get("cash", self.cash))
        self.packages = int(data.get("packages", self.packages))
        if "appearance" in data:
            self.appearance = normalize_character(data.get("appearance"))
        self.in_vehicle = bool(data.get("in_vehicle", getattr(self, "in_vehicle", False)))
        self.vehicle_id = str(data.get("vehicle_id", getattr(self, "vehicle_id", "")))
        self.vehicle_kind = str(data.get("vehicle_kind", getattr(self, "vehicle_kind", "")))
        self.vehicle_role = str(data.get("vehicle_role", getattr(self, "vehicle_role", "")))
        previous_interior_pos = (getattr(self, "interior_x", 0), getattr(self, "interior_y", 0))
        self.interior_id = str(data.get("interior_id", getattr(self, "interior_id", "")))
        self.interior_x = int(data.get("interior_x", getattr(self, "interior_x", 0)) or 0)
        self.interior_y = int(data.get("interior_y", getattr(self, "interior_y", 0)) or 0)
        self.interior_aim = float(data.get("interior_aim", getattr(self, "interior_aim", 0.0)) or 0.0)
        if (self.interior_x, self.interior_y) != previous_interior_pos:
            self.moving_until = time.monotonic() + 0.22
            self.anim_epoch = time.monotonic()
        self.level = int(float(data.get("level", getattr(self, "level", 0)) or 0))
        if snap_local:
            self.render_x = self.target_x
            self.render_y = self.target_y

    def smooth(self, dt: float, local: bool = False) -> None:
        strength = 22.0 if local else 13.0
        t = 1.0 - math.exp(-strength * dt)
        self.render_x += (self.target_x - self.render_x) * t
        self.render_y += (self.target_y - self.render_y) * t


class RemoteVehicle:
    def __init__(self, data: dict):
        self.id = str(data.get("id", "car"))
        self.render_x = float(data.get("x", 0.0))
        self.render_y = float(data.get("y", 0.0))
        self.target_x = self.render_x
        self.target_y = self.render_y
        self.angle = float(data.get("angle", 0.0))
        self.target_angle = self.angle
        self.speed = float(data.get("speed", 0.0))
        self.color_index = int(data.get("color", 0))
        self.sprite_index = int(data.get("sprite", self.color_index))
        self.vehicle_class = str(data.get("vehicle_class", "sedan"))
        self.collision_length = float(data.get("collision_length", TRAFFIC_CAR_LENGTH))
        self.collision_width = float(data.get("collision_width", TRAFFIC_CAR_WIDTH))
        self.render_length = int(data.get("render_length", 48))
        self.driver = str(data.get("driver", "npc"))
        self.passengers = int(data.get("passengers", 0))
        self.passenger_capacity = int(data.get("passenger_capacity", 3))
        self.parked = bool(data.get("parked", False))

    def update(self, data: dict) -> None:
        old_x, old_y = self.target_x, self.target_y
        new_x = float(data.get("x", self.target_x))
        new_y = float(data.get("y", self.target_y))
        new_speed = float(data.get("speed", self.speed))
        packet_angle = float(data.get("angle", self.target_angle))
        # Heading is authoritative for sprite nose/tail. If a stale packet ever
        # disagrees by roughly 180 degrees with clear vehicle motion, repair only
        # the render target. Reverse driving expects the nose opposite velocity.
        mdx, mdy = new_x-old_x, new_y-old_y
        if math.hypot(mdx, mdy) > 0.75 and abs(new_speed) > 8.0:
            motion_heading = math.atan2(mdy, mdx)
            expected = motion_heading if new_speed >= 0.0 else motion_heading + math.pi
            diff = (packet_angle-expected+math.pi)%(math.pi*2.0)-math.pi
            if abs(diff) > math.radians(120.0):
                packet_angle = expected
        self.target_x = new_x
        self.target_y = new_y
        self.target_angle = packet_angle
        self.speed = new_speed
        self.color_index = int(data.get("color", self.color_index))
        self.sprite_index = int(data.get("sprite", self.sprite_index))
        self.vehicle_class = str(data.get("vehicle_class", self.vehicle_class))
        self.collision_length = float(data.get("collision_length", self.collision_length))
        self.collision_width = float(data.get("collision_width", self.collision_width))
        self.render_length = int(data.get("render_length", self.render_length))
        self.driver = str(data.get("driver", self.driver))
        self.passengers = int(data.get("passengers", self.passengers))
        self.passenger_capacity = int(data.get("passenger_capacity", self.passenger_capacity))
        self.parked = bool(data.get("parked", self.parked))

    def smooth(self, dt: float) -> None:
        t = 1.0 - math.exp(-12.0 * dt)
        self.render_x += (self.target_x - self.render_x) * t
        self.render_y += (self.target_y - self.render_y) * t
        delta = (self.target_angle - self.angle + math.pi) % (math.pi * 2) - math.pi
        self.angle += delta * t


class RemoteBicycle:
    def __init__(self, data: dict):
        self.id = str(data.get("id", "bike"))
        self.render_x = float(data.get("x", 0.0))
        self.render_y = float(data.get("y", 0.0))
        self.target_x = self.render_x
        self.target_y = self.render_y
        self.angle = float(data.get("angle", 0.0))
        self.target_angle = self.angle
        self.speed = float(data.get("speed", 0.0))
        self.controlled_by = str(data.get("controlled_by", ""))
        self.rider = str(data.get("rider", "none"))
        self.parked = bool(data.get("parked", False))
        self.appearance = normalize_character(data.get("appearance"))
        self.anim_epoch = time.monotonic() + random.random() * 4.0

    def update(self, data: dict) -> None:
        self.target_x = float(data.get("x", self.target_x))
        self.target_y = float(data.get("y", self.target_y))
        self.target_angle = float(data.get("angle", self.target_angle))
        self.speed = float(data.get("speed", self.speed))
        self.controlled_by = str(data.get("controlled_by", self.controlled_by))
        self.rider = str(data.get("rider", self.rider))
        self.parked = bool(data.get("parked", self.parked))
        if "appearance" in data:
            self.appearance = normalize_character(data.get("appearance"))

    def smooth(self, dt: float) -> None:
        t = 1.0 - math.exp(-12.0 * dt)
        self.render_x += (self.target_x - self.render_x) * t
        self.render_y += (self.target_y - self.render_y) * t
        delta = (self.target_angle - self.angle + math.pi) % (math.pi * 2) - math.pi
        self.angle += delta * t


class RemoteNPC:
    def __init__(self, data: dict):
        self.id = str(data.get("id", "npc"))
        self.render_x = float(data.get("x", 0.0))
        self.render_y = float(data.get("y", 0.0))
        self.target_x = self.render_x
        self.target_y = self.render_y
        self.aim = float(data.get("aim", 0.0))
        self.appearance = normalize_character(data.get("appearance"))
        self.moving_until = time.monotonic() + 0.3
        self.anim_epoch = time.monotonic() + random.random() * 4.0

    def update(self, data: dict) -> None:
        nx = float(data.get("x", self.target_x))
        ny = float(data.get("y", self.target_y))
        if math.hypot(nx - self.target_x, ny - self.target_y) > 0.15:
            self.moving_until = time.monotonic() + 0.22
        self.target_x, self.target_y = nx, ny
        self.aim = float(data.get("aim", self.aim))
        if "appearance" in data:
            self.appearance = normalize_character(data.get("appearance"))

    def smooth(self, dt: float) -> None:
        t = 1.0 - math.exp(-10.0 * dt)
        self.render_x += (self.target_x - self.render_x) * t
        self.render_y += (self.target_y - self.render_y) * t


class Game:
    @staticmethod
    def _build_version_static() -> str:
        try:
            return (Path(__file__).resolve().parent / "VERSION.txt").read_text(encoding="utf-8").strip() or "unknown"
        except OSError:
            return "unknown"

    def __init__(self, uri: str, phone: str, name: str, appearance: dict | None = None, appearance_changed: bool = False):
        pygame.init()
        pygame.display.set_caption(f"Python MMO v{self._build_version_static()} - {uri}")
        self.screen = pygame.display.set_mode((SCREEN_W, SCREEN_H), pygame.RESIZABLE)
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("consolas", 19)
        self.small_font = pygame.font.SysFont("consolas", 15)
        self.tiny_font = pygame.font.SysFont("consolas", 12)
        self.big_font = pygame.font.SysFont("consolas", 28, bold=True)
        self.inv_title_font = pygame.font.SysFont("consolas", 31, bold=True)

        net_cls = BrowserNetworkClient if sys.platform == "emscripten" else NetworkClient
        self.network = net_cls(uri, phone, name, appearance, appearance_changed)
        self.network.start()
        self.local_id: str | None = None
        self.players: dict[str, RemotePlayer] = {}
        self.map_players: dict[str, dict] = {}
        self.vehicles: dict[str, RemoteVehicle] = {}
        self.bicycles: dict[str, RemoteBicycle] = {}
        self.npcs: dict[str, RemoteNPC] = {}
        self.blood_stains: dict[str, dict] = {}
        self.traffic_lights: dict[str, bool] = {}
        self.notice = "Connecting to Open Night Internet Server..." if ".railway.app" in uri.lower() else "Connecting..."
        self.notice_until = time.monotonic() + 4.0
        self.connected = False
        self.last_send = 0.0
        self._map_transfer_hash = ""
        self._map_transfer_chunks: list[bytes] = []
        self._map_transfer_expected_chunks = 0
        self.map_config = get_map(DEFAULT_MAP_ID)
        self.environment = EnvironmentRenderer(self.map_config)
        self.inventory = empty_inventory()
        self.inventory_open = False
        self.map_open = False
        self.chunk_debug_overlay = False
        self.issue_report_open = False
        self.issue_report_category = "art"
        self.issue_report_note = ""
        self.issue_report_snapshot = None
        self.interior = IsometricInterior()
        # Cache the expensive static world-map layer. Dynamic player/chunk
        # markers are drawn separately, so opening M is cheap and robust.
        self._world_map_cache = None
        self._world_map_cache_key = None
        self._world_map_last_error = ""
        self.server_chunk = (0, 0)
        self.server_region = (0, 0)
        self.server_region_id = "R1C1"
        self.interest_radius = int(self.map_config.get("interest_radius_chunks", 2))
        self.selected_slot = 0
        self.drag_source: int | None = None
        self.account_masked = ""
        self.settings = load_settings()
        self.camera_controller = LookAheadCamera(self.settings.get("camera", {}))
        self.pause_menu_open = False
        self.pause_page = "main"
        self.pause_scroll = 0
        self.friend_names = self.load_friend_names()
        self.chat_active = False
        self.chat_text = ""
        self.chat_bubbles: dict[str, dict] = {}
        self.style_watcher = StyleWatcher()
        self.settings_watcher = StyleWatcher(GAME_SETTINGS_PATH)
        self.art_style = load_art_style()
        hot = self.art_style.get("hot_reload", {})
        self.hot_reload_enabled = bool(hot.get("enabled", True))
        self.hot_reload_poll_seconds = float(hot.get("poll_seconds", 0.5))
        cam_cfg = self.settings.get("camera", {})
        self.camera_zoom = float(cam_cfg.get("zoom_default", 0.85))
        self.camera_zoom_min = float(cam_cfg.get("zoom_min", 0.55))
        self.camera_zoom_max = float(cam_cfg.get("zoom_max", 2.0))
        self.camera_zoom_step = float(cam_cfg.get("zoom_step", 0.10))
        self.camera_zoom = max(self.camera_zoom_min, min(self.camera_zoom_max, self.camera_zoom))
        self._zoom_world_surface = None
        self._zoom_world_surface_size = None
        self.camera_rotation_degrees = float(cam_cfg.get("rotation_default_degrees", 0.0))
        self.camera_rotation_enabled = bool(cam_cfg.get("rotation_enabled", True))
        self.camera_rotation_sensitivity = float(cam_cfg.get("rotation_sensitivity_deg_per_px", 0.32))
        self.camera_rotation_snap = max(0.0, float(cam_cfg.get("rotation_snap_degrees", 0.0)))
        self.camera_center_player_when_rotated = bool(cam_cfg.get("center_player_when_rotated", True))
        self.camera_rotation_dragging = False
        self._render_camera_override = None
        # v2.3 action controls. Jump is a one-shot request; crouch is held.
        # Head look remains render-only/client-side and is never transmitted.
        self.jump_request_pending = False
        self.sprint_active = False
        self.sprint_trigger_key: int | None = None
        self.last_direction_tap: dict[int, float] = {}

    def load_friend_names(self) -> dict[str, str]:
        friends: dict[str, str] = {}
        try:
            with FRIENDS_PATH.open("r", encoding="utf-8-sig", newline="") as handle:
                for row in csv.DictReader(handle):
                    name = str(row.get("name", "")).strip()[:24]
                    if name:
                        friends[name.casefold()] = name
        except OSError:
            pass
        return friends

    def is_friend(self, name: str) -> bool:
        return str(name).strip().casefold() in self.friend_names

    def toggle_friend(self, name: str) -> None:
        clean = str(name).strip()[:24]
        if not clean:
            return
        key = clean.casefold()
        if key in self.friend_names:
            del self.friend_names[key]
            action = "Removed"
        else:
            self.friend_names[key] = clean
            action = "Added"
        try:
            FRIENDS_PATH.parent.mkdir(parents=True, exist_ok=True)
            with FRIENDS_PATH.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["name"])
                writer.writeheader()
                for saved in sorted(self.friend_names.values(), key=str.casefold):
                    writer.writerow({"name": saved})
        except OSError:
            # Browser builds keep the list for the current play session even if
            # their virtual filesystem does not persist writes.
            pass
        self.notice = f"{action} {clean} {'to' if action == 'Added' else 'from'} friends"
        self.notice_until = time.monotonic() + 2.0

    def submit_chat(self) -> None:
        raw = self.chat_text.strip()
        self.chat_active = False
        self.chat_text = ""
        if not raw:
            return
        command = raw.casefold()
        if command == "/bug" or command.startswith("/bug "):
            description = raw[4:].strip()
            if not description:
                self.notice = "Bug format: /bug describe what went wrong"
                self.notice_until = time.monotonic() + 3.5
                return
            self.issue_report_category = "bug"
            self.issue_report_note = description
            self.issue_report_snapshot = self.screen.copy()
            self.save_current_issue_report(source="chat_/bug")
            return
        if raw.casefold().startswith("/w "):
            rest = raw[3:].strip()
            target = next(
                (name for name in sorted(self.friend_names.values(), key=len, reverse=True)
                 if rest.casefold().startswith(name.casefold() + " ")),
                None,
            )
            if target is None:
                self.notice = "Whisper format: /w FriendName message — add them in Esc > Friends first"
                self.notice_until = time.monotonic() + 3.5
                return
            text = rest[len(target):].strip()
            if text:
                self.network.send({"type": "chat", "scope": "whisper", "target": target, "text": text[:120]})
            return
        self.network.send({"type": "chat", "scope": "local", "text": raw[:120]})

    def handle_chat_key(self, event: pygame.event.Event) -> bool:
        if not self.chat_active:
            return False
        if event.key == pygame.K_ESCAPE:
            self.chat_active = False
            self.chat_text = ""
        elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            self.submit_chat()
        elif event.key == pygame.K_BACKSPACE:
            self.chat_text = self.chat_text[:-1]
        elif event.unicode and event.unicode.isprintable() and len(self.chat_text) < (400 if self.chat_text.casefold().startswith("/bug") else 140):
            self.chat_text += event.unicode
        return True

    def cancel_direction_sprint(self) -> None:
        self.sprint_active = False
        self.sprint_trigger_key = None

    def register_direction_tap(self, key: int, now: float | None = None) -> bool:
        direction_keys = (
            pygame.K_w, pygame.K_a, pygame.K_s, pygame.K_d,
            pygame.K_UP, pygame.K_LEFT, pygame.K_DOWN, pygame.K_RIGHT,
        )
        if key not in direction_keys:
            return False
        local = self.players.get(self.local_id or "")
        blocked = (
            self.pause_menu_open or self.issue_report_open or self.inventory_open
            or self.map_open or self.interior.active or self.network.fatal
            or bool(getattr(local, "in_vehicle", False))
        )
        timestamp = time.monotonic() if now is None else float(now)
        if blocked:
            self.last_direction_tap.pop(key, None)
            return False
        previous = self.last_direction_tap.get(key)
        self.last_direction_tap[key] = timestamp
        window = float(self.settings.get("movement", {}).get("sprint_double_tap_window_seconds", 0.30))
        if previous is not None and 0.0 <= timestamp - previous <= window:
            self.sprint_active = True
            self.sprint_trigger_key = key
            self.last_direction_tap.pop(key, None)
            self.notice = "RUNNING 3× — keep the twice-tapped direction held"
            self.notice_until = time.monotonic() + 1.5
            return True
        return False

    def _build_version(self) -> str:
        try:
            return (Path(__file__).resolve().parent / "VERSION.txt").read_text(encoding="utf-8").strip() or "unknown"
        except OSError:
            return "unknown"

    def open_issue_reporter(self) -> None:
        self.issue_report_open = True
        self.issue_report_category = "art"
        self.issue_report_note = ""
        self.issue_report_snapshot = self.screen.copy()
        self.notice = "Issue reporter opened — 1 Art / 2 AI / 3 Collision-Nav / 4 Other"
        self.notice_until = time.monotonic() + 2.0

    def _nearest_ai_context(self, x: float, y: float) -> tuple[str, str, float]:
        candidates: list[tuple[float, str, str]] = []
        for npc in self.npcs.values():
            candidates.append((math.hypot(npc.render_x - x, npc.render_y - y), "npc", str(npc.id)))
        for car in self.vehicles.values():
            if str(getattr(car, "driver", "npc")) == "npc":
                candidates.append((math.hypot(car.render_x - x, car.render_y - y), "traffic", str(car.id)))
        for bike in self.bicycles.values():
            if str(getattr(bike, "rider", "none")) not in {"player", "local"}:
                candidates.append((math.hypot(bike.render_x - x, bike.render_y - y), "bicycle", str(bike.id)))
        if not candidates:
            return "", "", -1.0
        distance, kind, entity_id = min(candidates, key=lambda row: row[0])
        return kind, entity_id, distance

    def save_current_issue_report(self, source: str = "f10") -> None:
        local = self.players.get(self.local_id or "")
        if local is None:
            self.notice = "Cannot report yet — local player position unavailable"
            self.notice_until = time.monotonic() + 2.0
            return
        x, y = float(local.render_x), float(local.render_y)
        cx, cy = world_to_chunk(x, y, self.map_config)
        chunk_size = max(1, int(self.map_config.get("chunk_size", 1024)))
        local_x = x - cx * chunk_size
        local_y = y - cy * chunk_size
        ai_kind, ai_id, ai_distance = self._nearest_ai_context(x, y)
        payload = {
            "source": source,
            "reporter": str(getattr(self.network, "name", ""))[:24],
            "description": self.issue_report_note.strip(),
            "target_version": "next",
            "duplicate_of": "",
            "build_version": self._build_version(),
            "status": "open",
            "category": self.issue_report_category,
            "note": self.issue_report_note.strip(),
            "map_id": str(self.map_config.get("id", "")),
            "map_name": str(self.map_config.get("name", "")),
            "chunk_id": chunk_label(cx, cy),
            "chunk_x": cx,
            "chunk_y": cy,
            "world_x": x,
            "world_y": y,
            "local_x": local_x,
            "local_y": local_y,
            "camera_rotation_deg": float(self.camera_rotation_degrees % 360.0),
            "camera_zoom": float(self.camera_zoom),
            "in_vehicle": bool(getattr(local, "in_vehicle", False)),
            "vehicle_id": str(getattr(local, "vehicle_id", "")),
            "nearest_ai_kind": ai_kind,
            "nearest_ai_id": ai_id,
            "nearest_ai_distance": ai_distance if ai_distance >= 0 else "",
        }
        try:
            capture = self.issue_report_snapshot if self.issue_report_snapshot is not None else self.screen
            _, shot_path, feedback_csv, feedback_shot = save_issue_report(capture, payload)
        except Exception as exc:
            self.notice = f"Issue report failed: {exc}"
            self.notice_until = time.monotonic() + 3.0
            return
        self.issue_report_open = False
        self.issue_report_note = ""
        self.issue_report_snapshot = None
        if feedback_csv is not None and feedback_shot is not None:
            self.notice = f"Bug saved — feedback\\next_version\\screenshots\\{feedback_shot.name}"
        else:
            self.notice = f"Flagged {payload['category'].upper()} issue in {payload['chunk_id']} — {shot_path.name}"
        self.notice_until = time.monotonic() + 3.0

    def handle_issue_report_key(self, event: pygame.event.Event) -> bool:
        """Handle F10 report modal keys. Returns True when the event is consumed."""
        if event.key == pygame.K_F10:
            if self.issue_report_open:
                self.issue_report_open = False
                self.issue_report_snapshot = None
            else:
                self.open_issue_reporter()
            return True
        if not self.issue_report_open:
            return False
        if event.key == pygame.K_ESCAPE:
            self.issue_report_open = False
            self.issue_report_note = ""
            self.issue_report_snapshot = None
            return True
        if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            self.save_current_issue_report()
            return True
        category_keys = {
            pygame.K_1: "art",
            pygame.K_KP1: "art",
            pygame.K_2: "ai",
            pygame.K_KP2: "ai",
            pygame.K_3: "collision_nav",
            pygame.K_KP3: "collision_nav",
            pygame.K_4: "other",
            pygame.K_KP4: "other",
        }
        if event.key in category_keys:
            self.issue_report_category = category_keys[event.key]
            return True
        if event.key == pygame.K_BACKSPACE:
            self.issue_report_note = self.issue_report_note[:-1]
            return True
        if event.unicode and event.unicode.isprintable() and len(self.issue_report_note) < 96:
            self.issue_report_note += event.unicode
            return True
        return True

    def draw_issue_reporter(self) -> None:
        if not self.issue_report_open:
            return
        sw, sh = self.screen.get_size()
        shade = pygame.Surface((sw, sh), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 150))
        self.screen.blit(shade, (0, 0))
        panel = pygame.Rect(0, 0, min(720, sw - 60), 300)
        panel.center = (sw // 2, sh // 2)
        ui = self.art_style.get("ui", {})
        panel_color = tuple(ui.get("panel", (28,31,31)))
        accent = tuple(ui.get("accent", INV_SELECTED))
        pygame.draw.rect(self.screen, panel_color, panel, border_radius=8)
        pygame.draw.rect(self.screen, accent, panel, width=3, border_radius=8)
        title = self.big_font.render("FLAG AREA FOR NEXT VERSION", True, TEXT_COLOR)
        self.screen.blit(title, (panel.x + 24, panel.y + 20))
        local = self.players.get(self.local_id or "")
        if local is not None:
            cx, cy = world_to_chunk(local.render_x, local.render_y, self.map_config)
            size = max(1, int(self.map_config.get("chunk_size", 1024)))
            coord = f"{chunk_label(cx, cy)} @ ({int(local.render_x-cx*size)}, {int(local.render_y-cy*size)})   world ({int(local.render_x)}, {int(local.render_y)})"
        else:
            coord = "Position unavailable"
        self.screen.blit(self.small_font.render(coord, True, MUTED_TEXT), (panel.x + 26, panel.y + 62))
        options = [("1", "art"), ("2", "ai"), ("3", "collision_nav"), ("4", "other")]
        x = panel.x + 26
        y = panel.y + 102
        for key, category in options:
            selected = self.issue_report_category == category
            label = category.replace("_", "/").upper()
            text_surf = self.small_font.render(f"[{key}] {label}", True, accent if selected else TEXT_COLOR)
            self.screen.blit(text_surf, (x, y))
            x += text_surf.get_width() + 30
        note_label = self.small_font.render("Note (optional):", True, TEXT_COLOR)
        self.screen.blit(note_label, (panel.x + 26, panel.y + 150))
        note_rect = pygame.Rect(panel.x + 26, panel.y + 178, panel.width - 52, 42)
        pygame.draw.rect(self.screen, (16,18,18), note_rect, border_radius=5)
        pygame.draw.rect(self.screen, MUTED_TEXT, note_rect, width=1, border_radius=5)
        shown = self.issue_report_note or "type a short description..."
        note_color = TEXT_COLOR if self.issue_report_note else MUTED_TEXT
        note_surf = self.small_font.render(shown[-88:], True, note_color)
        self.screen.blit(note_surf, (note_rect.x + 10, note_rect.y + 11))
        footer = self.small_font.render("ENTER save report + PNG screenshot    F10/ESC cancel", True, MUTED_TEXT)
        self.screen.blit(footer, (panel.x + 26, panel.bottom - 48))

    def camera(self) -> tuple[float, float]:
        if self._render_camera_override is not None:
            cam = self._render_camera_override
        else:
            cam = self.camera_controller.position()
        if bool(self.settings.get("render", {}).get("camera_pixel_snap", True)):
            return float(round(cam[0])), float(round(cam[1]))
        return cam

    def camera_center(self) -> tuple[float, float]:
        return self.camera_controller.center(self.logical_view_size())

    def camera_depth(self, x: float, y: float) -> float:
        theta = math.radians(self.camera_rotation_degrees)
        return -math.sin(theta) * float(x) + math.cos(theta) * float(y)

    def adjust_camera_rotation(self, mouse_dx: float) -> None:
        if not self.camera_rotation_enabled:
            return
        self.camera_rotation_degrees = (self.camera_rotation_degrees - float(mouse_dx) * self.camera_rotation_sensitivity) % 360.0
        # Rebuilding camera-aware 2.5D chunk art during every mouse-motion event
        # was the main rotation hitch. Keep the static chunk art stable while
        # dragging; finish_camera_rotation() applies the final extrusion bucket.
        if not bool(self.settings.get("render", {}).get("defer_25d_rotation_while_dragging", True)):
            setter = getattr(self.environment, "set_view_rotation", None)
            if callable(setter):
                setter(self.camera_rotation_degrees)

    def finish_camera_rotation(self) -> None:
        snap = float(self.camera_rotation_snap)
        if snap > 0.0:
            self.camera_rotation_degrees = (round(self.camera_rotation_degrees / snap) * snap) % 360.0
        setter = getattr(self.environment, "set_view_rotation", None)
        if callable(setter):
            setter(self.camera_rotation_degrees)

    def logical_view_size(self) -> tuple[int, int]:
        sw, sh = self.screen.get_size()
        z = max(0.05, float(self.camera_zoom))
        return max(320, int(math.ceil(sw / z))), max(240, int(math.ceil(sh / z)))

    def logical_mouse_pos(self) -> tuple[int, int]:
        mx, my = pygame.mouse.get_pos()
        z = max(0.05, float(self.camera_zoom))
        return int(mx / z), int(my / z)

    def adjust_camera_zoom(self, wheel_y: int) -> None:
        if not wheel_y:
            return
        old = self.camera_zoom
        self.camera_zoom = max(self.camera_zoom_min, min(self.camera_zoom_max, old + float(wheel_y) * self.camera_zoom_step))
        if abs(self.camera_zoom - old) > 1e-6:
            self.camera_controller.reset()
            self.notice = f"Camera zoom {self.camera_zoom:.2f}x"
            self.notice_until = time.monotonic() + 1.2

    def update_camera(self, dt: float) -> None:
        local = self.players.get(self.local_id or "")
        if local is None:
            return
        world_w = float(self.map_config.get("world_w", self.screen.get_width()))
        world_h = float(self.map_config.get("world_h", self.screen.get_height()))
        self.camera_controller.update(
            (local.render_x, local.render_y),
            self.logical_mouse_pos(),
            self.logical_view_size(),
            (world_w, world_h),
            dt,
            driving=bool(getattr(local, "in_vehicle", False)),
            view_rotation_degrees=self.camera_rotation_degrees,
            force_center=bool(self.camera_rotation_dragging or (self.camera_center_player_when_rotated and self.camera_rotation_enabled and abs(self.camera_rotation_degrees % 360.0) > 0.01)),
        )

    def world_to_screen(self, x: float, y: float) -> tuple[int, int]:
        cam_x, cam_y = self.camera()
        return int(float(x) - cam_x), int(float(y) - cam_y)

    def screen_to_world(self, x: float, y: float) -> tuple[float, float]:
        z = max(0.05, float(self.camera_zoom))
        lx, ly = float(x) / z, float(y) / z
        vw, vh = self.logical_view_size()
        dx, dy = lx - vw * 0.5, ly - vh * 0.5
        theta = math.radians(self.camera_rotation_degrees)
        c, sn = math.cos(theta), math.sin(theta)
        # Inverse of the final whole-scene pygame rotation.
        source_dx = c * dx - sn * dy
        source_dy = sn * dx + c * dy
        rotation_active = self.camera_rotation_enabled and abs(self.camera_rotation_degrees % 360.0) > 0.01
        local = self.players.get(self.local_id or "")
        if rotation_active and local is not None:
            cx, cy = float(local.render_x), float(local.render_y)
        else:
            cx, cy = self.camera_controller.center((vw, vh))
        return cx + source_dx, cy + source_dy

    def process_network(self) -> None:
        pump = getattr(self.network, "pump", None)
        if callable(pump):
            pump()
        while True:
            try:
                message = self.network.incoming.get_nowait()
            except queue.Empty:
                break
            kind = message.get("type")
            if kind == "connection":
                self.connected = bool(message.get("connected"))
                if not self.connected and not self.network.fatal:
                    self.notice = "Disconnected - reconnecting..."
                    self.notice_until = time.monotonic() + 2.0
            elif kind == "login_error":
                self.notice = "LOGIN FAILED: " + str(message.get("text", "Unknown login error"))
                self.notice_until = float("inf")
            elif kind == "map_transfer_begin":
                self._map_transfer_hash = str(message.get("map_hash", ""))
                self._map_transfer_chunks = []
                self._map_transfer_expected_chunks = int(message.get("chunks", 0) or 0)
                self.notice = f"Downloading map + textures: {message.get('display_name','portable map')}"
                self.notice_until = time.monotonic() + 30.0
            elif kind == "map_transfer_chunk":
                if str(message.get("map_hash", "")) == self._map_transfer_hash:
                    try:
                        self._map_transfer_chunks.append(base64.b64decode(str(message.get("data", ""))))
                    except Exception:
                        self._map_transfer_chunks = []
            elif kind == "map_transfer_end":
                digest = str(message.get("map_hash", ""))
                try:
                    if digest != self._map_transfer_hash or (self._map_transfer_expected_chunks and len(self._map_transfer_chunks) != self._map_transfer_expected_chunks):
                        raise ValueError("incomplete map transfer")
                    install_transfer_bundle(b"".join(self._map_transfer_chunks), digest)
                    self.notice = f"Map cached locally: {digest[:12]}…"
                    self.notice_until = time.monotonic() + 4.0
                except Exception as exc:
                    self.notice = f"Map cache install failed: {exc}"
                    self.notice_until = float("inf")
                finally:
                    self._map_transfer_chunks = []
                    self._map_transfer_hash = ""
            elif kind == "welcome":
                self.local_id = message["id"]
                incoming_map = message.get("map")
                if isinstance(incoming_map, dict) and incoming_map.get("world_w"):
                    if incoming_map.get("map_payload_mode") == "portable_map_v1":
                        digest = str(incoming_map.get("map_hash", ""))
                        try:
                            local_cfg = load_cached_map(digest)
                            for key, value in incoming_map.items():
                                if key not in {"map_payload_mode", "map_hash"}: local_cfg[key] = value
                            self.map_config = local_cfg
                        except Exception as exc:
                            self.notice = f"Portable map cache unavailable: {exc}"
                            self.notice_until = float("inf")
                            self.map_config = get_map(DEFAULT_MAP_ID)
                    elif incoming_map.get("map_payload_mode") == "local_chunked_v1":
                        # Large-world contract: static authored geometry is packaged
                        # locally and streamed from the client's chunk cache. Login
                        # receives only metadata, keeping packet size independent of
                        # the total number of NYC chunks.
                        local_cfg = get_map(str(incoming_map.get("id", DEFAULT_MAP_ID)))
                        local_build = str(local_cfg.get("map_build_id", ""))
                        server_build = str(incoming_map.get("map_build_id", ""))
                        if server_build and local_build and server_build != local_build:
                            self.notice = f"Map data mismatch: client {local_build} / server {server_build}"
                            self.notice_until = float("inf")
                        for key, value in incoming_map.items():
                            if key != "map_payload_mode":
                                local_cfg[key] = value
                        self.map_config = local_cfg
                    else:
                        buildings = incoming_map.get("buildings", []) or []
                        building_ids = incoming_map.get("building_ids", []) or []
                        incoming_map["building_id_by_rect"] = {
                            tuple(rect): str(bid) for rect, bid in zip(buildings, building_ids)
                            if isinstance(rect, (list, tuple)) and len(rect) >= 4
                        }
                        self.map_config = incoming_map
                    self.environment.set_map(self.map_config)
                    self._world_map_cache = None
                    self._world_map_cache_key = None
                    self.interest_radius = int(self.map_config.get("interest_radius_chunks", 2))
                    self.camera_controller.reset()
                player = RemotePlayer(message["player"])
                self.players[player.id] = player
                self.map_players[player.id] = {
                    "id": player.id, "name": player.name,
                    "x": player.target_x, "y": player.target_y,
                    "level": player.level,
                }
                self.inventory = normalize_inventory(message.get("inventory"))
                self.account_masked = str(message.get("account", {}).get("phone_masked", ""))
                self.notice = "Connected. WASD world-move; double-tap a direction for 3× run; Space jump; C crouch; MMB rotates; wheel zooms; T vehicle; E interact; I inventory; M map; ESC options."
                self.notice_until = time.monotonic() + 4.0
            elif kind == "inventory":
                self.inventory = normalize_inventory(message.get("slots"))
                local = self.players.get(self.local_id or "")
                if local is not None:
                    local.cash = int(message.get("cash", local.cash))
                    local.packages = int(message.get("package_count", local.packages))
            elif kind == "snapshot":
                seen: set[str] = set()
                for data in message.get("players", []):
                    pid = data["id"]
                    seen.add(pid)
                    if pid not in self.players:
                        self.players[pid] = RemotePlayer(data)
                    self.players[pid].update_from_snapshot(data)
                for pid in list(self.players):
                    if pid not in seen and pid != self.local_id:
                        del self.players[pid]
                map_rows = message.get("map_players")
                if isinstance(map_rows, list):
                    global_markers: dict[str, dict] = {}
                    for row in map_rows:
                        if not isinstance(row, dict):
                            continue
                        pid = str(row.get("id", "")).strip()
                        if not pid:
                            continue
                        try:
                            x, y = float(row.get("x", 0.0)), float(row.get("y", 0.0))
                            level = int(float(row.get("level", 0) or 0))
                        except (TypeError, ValueError):
                            continue
                        if math.isfinite(x) and math.isfinite(y):
                            global_markers[pid] = {
                                "id": pid,
                                "name": str(row.get("name", "Player"))[:24],
                                "x": x, "y": y, "level": level,
                                "in_vehicle": bool(row.get("in_vehicle", False)),
                            }
                    self.map_players = global_markers
                seen_cars: set[str] = set()
                for data in message.get("vehicles", []):
                    car_id = str(data.get("id", ""))
                    if not car_id:
                        continue
                    seen_cars.add(car_id)
                    if car_id not in self.vehicles:
                        self.vehicles[car_id] = RemoteVehicle(data)
                    self.vehicles[car_id].update(data)
                for car_id in list(self.vehicles):
                    if car_id not in seen_cars:
                        del self.vehicles[car_id]
                seen_bikes: set[str] = set()
                for data in message.get("bicycles", []):
                    bike_id = str(data.get("id", ""))
                    if not bike_id:
                        continue
                    seen_bikes.add(bike_id)
                    if bike_id not in self.bicycles:
                        self.bicycles[bike_id] = RemoteBicycle(data)
                    self.bicycles[bike_id].update(data)
                for bike_id in list(self.bicycles):
                    if bike_id not in seen_bikes:
                        del self.bicycles[bike_id]
                seen_npcs: set[str] = set()
                for data in message.get("npcs", []):
                    nid = str(data.get("id", ""))
                    if not nid:
                        continue
                    seen_npcs.add(nid)
                    if nid not in self.npcs:
                        self.npcs[nid] = RemoteNPC(data)
                    self.npcs[nid].update(data)
                for nid in list(self.npcs):
                    if nid not in seen_npcs:
                        del self.npcs[nid]
                blood_rows = message.get("blood_stains", [])
                if isinstance(blood_rows, list):
                    self.blood_stains = {
                        str(row.get("id")): row for row in blood_rows
                        if isinstance(row, dict) and row.get("id")
                    }
                lights = message.get("traffic_lights")
                if isinstance(lights, dict):
                    self.traffic_lights = {str(k): bool(v) for k, v in lights.items()}
                chunk = message.get("chunk")
                if isinstance(chunk, (list, tuple)) and len(chunk) >= 2:
                    try:
                        self.server_chunk = (int(chunk[0]), int(chunk[1]))
                    except (TypeError, ValueError):
                        pass
                region = message.get("region")
                if isinstance(region, (list, tuple)) and len(region) >= 2:
                    try:
                        self.server_region = (int(region[0]), int(region[1]))
                    except (TypeError, ValueError):
                        pass
                self.server_region_id = str(message.get("region_id", self.server_region_id))
                try:
                    self.interest_radius = int(message.get("interest_radius", self.interest_radius))
                except (TypeError, ValueError):
                    pass
                local = self.players.get(self.local_id or "")
                if local is not None:
                    self.apply_interior_state(
                        bool(local.interior_id), local.interior_id,
                        local.interior_x, local.interior_y, local.interior_aim,
                    )
            elif kind == "interior_state":
                self.apply_interior_state(
                    bool(message.get("active", False)),
                    str(message.get("interior_id", "")),
                    int(message.get("x", 0) or 0),
                    int(message.get("y", 0) or 0),
                    float(message.get("aim", 0.0) or 0.0),
                    str(message.get("name", "")),
                )
            elif kind == "chat":
                sender_id = str(message.get("sender_id", ""))
                if sender_id:
                    self.chat_bubbles[sender_id] = {
                        "text": str(message.get("text", ""))[:120],
                        "scope": str(message.get("scope", "local")),
                        "until": time.monotonic() + 5.5,
                    }
            elif kind == "notice":
                self.notice = str(message.get("text", ""))
                self.notice_until = time.monotonic() + 3.0

    def input_vector(self) -> tuple[float, float]:
        # v2.4.1: on-foot WASD is camera-relative again: W is always screen-up /
        # camera-forward after the view is rotated. Vehicle input deliberately stays
        # raw so W/S remain throttle/reverse and A/D remain steering.
        blocked_ui = self.inventory_open or self.interior.active or self.network.fatal or self.pause_menu_open or self.issue_report_open
        x, y = movement_vector(blocked=blocked_ui)
        if blocked_ui:
            return x, y
        local = self.players.get(self.local_id or "")
        if local is not None and bool(getattr(local, "in_vehicle", False)):
            return x, y
        if not bool(self.settings.get("controls", {}).get("camera_relative_movement", True)):
            return x, y
        if abs(self.camera_rotation_degrees) < 1e-6:
            return x, y
        theta = math.radians(self.camera_rotation_degrees)
        c, sn = math.cos(theta), math.sin(theta)
        return c * x - sn * y, sn * x + c * y

    def send_input(self) -> None:
        now = time.monotonic()
        if now - self.last_send < 1.0 / NETWORK_SEND_RATE:
            return
        self.last_send = now
        x, y = self.input_vector()
        keys = pygame.key.get_pressed()
        blocked_actions = self.pause_menu_open or self.issue_report_open or self.inventory_open or self.map_open or self.interior.active or self.chat_active
        crouch = bool(keys[pygame.K_c]) and not blocked_actions

        # Multiplayer aim is the authoritative body/world heading. Mouse movement
        # affects camera look-ahead only and never changes the character pose.
        local = self.players.get(self.local_id or "")
        in_vehicle = bool(getattr(local, "in_vehicle", False)) if local is not None else False
        trigger_held = self.sprint_trigger_key is not None and bool(keys[self.sprint_trigger_key])
        if self.sprint_active and (not trigger_held or blocked_actions or crouch or self.jump_request_pending or in_vehicle or math.hypot(x, y) <= 0.05):
            self.cancel_direction_sprint()
        shift_boost = bool(keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT])
        if in_vehicle:
            boost = bool(not blocked_actions and shift_boost)
        else:
            boost = bool(
                not blocked_actions
                and not crouch
                and not self.jump_request_pending
                and (shift_boost or (self.sprint_active and trigger_held))
            )
        body_aim = float(getattr(local, "move_heading", getattr(local, "aim", 0.0))) if local is not None else 0.0
        if math.hypot(x, y) > 0.05 and not in_vehicle:
            body_aim = math.atan2(y, x)

        payload = {
            "type": "input", "x": x, "y": y, "aim": body_aim, "boost": boost,
            "crouch": crouch, "jump": bool(self.jump_request_pending and not blocked_actions),
        }
        self.network.send(payload)
        self.jump_request_pending = False

    @staticmethod
    def _dashed_line(surface: pygame.Surface, color, start, end, dash: int = 26, gap: int = 22, width: int = 2) -> None:
        x1, y1 = start
        x2, y2 = end
        dx, dy = x2 - x1, y2 - y1
        length = math.hypot(dx, dy)
        if length <= 1:
            return
        ux, uy = dx / length, dy / length
        pos = 0.0
        while pos < length:
            end_pos = min(length, pos + dash)
            a = (int(x1 + ux * pos), int(y1 + uy * pos))
            b = (int(x1 + ux * end_pos), int(y1 + uy * end_pos))
            pygame.draw.line(surface, color, a, b, width)
            pos += dash + gap

    def draw_traffic_signal(self, signal: dict) -> None:
        sx, sy = self.world_to_screen(float(signal["pos"][0]), float(signal["pos"][1]))
        green = bool(self.traffic_lights.get(str(signal.get("id")), False))
        # Crosswalk geometry is rendered once by EnvironmentRenderer from
        # crosswalks.csv. Traffic signals now render only their live light state.
        pygame.draw.circle(self.screen, (18, 20, 20), (sx + 22, sy - 22), 8)
        pygame.draw.circle(self.screen, (77, 210, 91) if green else (218, 64, 58), (sx + 22, sy - 22), 5)

    def nearest_interior(self, max_distance: float = 105.0) -> dict | None:
        local = self.players.get(self.local_id or "")
        if local is None:
            return None
        best = None
        best_d = float(max_distance)
        for info in self.map_config.get("interiors", []) or []:
            try:
                ex, ey = float(info["entry"][0]), float(info["entry"][1])
            except (KeyError, TypeError, ValueError, IndexError):
                continue
            d = math.hypot(local.render_x - ex, local.render_y - ey)
            if d <= best_d:
                best, best_d = info, d
        return best

    def interior_info(self, interior_id: str) -> dict | None:
        wanted = str(interior_id).strip()
        return next(
            (info for info in self.map_config.get("interiors", []) or []
             if str(info.get("id", "")).strip() == wanted),
            None,
        )

    def apply_interior_state(
        self, active: bool, interior_id: str, x: int, y: int, aim: float,
        title: str = "",
    ) -> None:
        """Mirror the server-authoritative room and tile into the local view."""
        if not active or not interior_id:
            if self.interior.active:
                self.interior.leave()
            return
        info = self.interior_info(interior_id)
        room_title = title or (str(info.get("name", "")) if info else "")
        if not self.interior.active or self.interior.room_id != interior_id:
            self.inventory_open = False
            self.map_open = False
            self.interior.enter(interior_id, room_title or None)
        self.interior.set_player_state(x, y, aim)

    def try_enter_interior(self) -> bool:
        info = self.nearest_interior()
        if info is None:
            return False
        self.inventory_open = False
        self.map_open = False
        self.network.send({"type": "interior_enter", "interior_id": str(info.get("id", "room"))})
        # Immediately send zero movement so the authoritative outside avatar stops.
        local = self.players.get(self.local_id or "")
        body_aim = float(getattr(local, "move_heading", getattr(local, "aim", 0.0))) if local is not None else 0.0
        self.network.send({"type": "input", "x": 0.0, "y": 0.0, "aim": body_aim})
        self.notice = f"Entering {str(info.get('name', 'building'))}..."
        self.notice_until = time.monotonic() + 1.5
        return True

    def draw_interior_entries(self) -> None:
        for info in self.map_config.get("interiors", []) or []:
            try:
                ex, ey = float(info["entry"][0]), float(info["entry"][1])
            except (KeyError, TypeError, ValueError, IndexError):
                continue
            sx, sy = self.world_to_screen(ex, ey)
            if -40 <= sx <= self.screen.get_width()+40 and -40 <= sy <= self.screen.get_height()+40:
                pygame.draw.rect(self.screen, (28, 30, 30), pygame.Rect(sx-13, sy-15, 26, 30), border_radius=2)
                pygame.draw.rect(self.screen, (207, 180, 86), pygame.Rect(sx-10, sy-12, 20, 27), width=2)
                pygame.draw.circle(self.screen, (226, 205, 124), (sx+5, sy+2), 2)
        info = self.nearest_interior()
        if info is not None:
            txt = self.font.render(f"[E] ENTER {str(info.get('name','BUILDING')).upper()}", True, (241, 221, 116))
            r = txt.get_rect(center=(self.screen.get_width()//2, self.screen.get_height()-108))
            pygame.draw.rect(self.screen, (9, 10, 10), r.inflate(24, 14), border_radius=5)
            self.screen.blit(txt, r)

    def draw_bike_lanes(self) -> None:
        """Draw lightweight protected/painted bike-lane overlays from map data."""
        for lane in self.map_config.get("bike_lanes", []) or []:
            raw = lane.get("points", []) or []
            if len(raw) < 2:
                continue
            points = [self.world_to_screen(float(p[0]), float(p[1])) for p in raw]
            try:
                width = max(8, min(24, int(float(lane.get("width", 16)))))
            except (TypeError, ValueError):
                width = 16
            # Dark border gives the lane separation from road asphalt; muted green
            # keeps it readable without becoming a bright modern-map overlay.
            pygame.draw.lines(self.screen, (35, 55, 42), False, points, width + 4)
            pygame.draw.lines(self.screen, (62, 112, 72), False, points, width)
            for a, b in zip(points, points[1:]):
                self._dashed_line(self.screen, (195, 203, 184), a, b, dash=12, gap=20, width=1)

    def draw_world(self) -> None:
        # Static city geometry is pre-rendered from the approved environment texture
        # atlas once per map. Collision/traffic data remains server-authoritative
        # and independent of this visual layer.
        self.environment.draw_view(self.screen, self.camera())
        self.draw_bike_lanes()

        # Traffic signals remain dynamic because their state is synchronized
        # by the authoritative server.
        for signal in self.map_config.get("traffic_signals", []):
            self.draw_traffic_signal(signal)

        self.draw_interior_entries()
        self.draw_location(tuple(self.map_config["supplier_pos"]), SUPPLIER_COLOR, "SUPPLIER", f"BUY ${BUY_PRICE}")
        self.draw_landmarks()

    def draw_landmarks(self) -> None:
        """Small in-world landmark markers; the full context lives on the M map."""
        w, h = self.screen.get_size()
        for landmark in self.map_config.get("landmarks", []):
            pos = landmark.get("pos", [0, 0])
            sx, sy = self.world_to_screen(float(pos[0]), float(pos[1]))
            if sx < -80 or sy < -50 or sx > w + 80 or sy > h + 50:
                continue
            kind = str(landmark.get("kind", "landmark"))
            color = (226, 202, 86) if kind in {"bridge", "landmark"} else (190, 196, 194)
            pygame.draw.circle(self.screen, (15, 16, 16), (sx, sy), 8)
            pygame.draw.circle(self.screen, color, (sx, sy), 5)
            label = self.tiny_font.render(str(landmark.get("name", "Landmark")), True, TEXT_COLOR)
            self.screen.blit(label, (sx + 10, sy - label.get_height() // 2))

    @staticmethod
    def _safe_map_point(point, world_w: float, world_h: float) -> tuple[float, float] | None:
        """Return a finite, clamped world-map point or None for malformed data."""
        try:
            x = float(point[0])
            y = float(point[1])
        except (TypeError, ValueError, IndexError, KeyError):
            return None
        if not (math.isfinite(x) and math.isfinite(y)):
            return None
        return max(0.0, min(world_w, x)), max(0.0, min(world_h, y))

    def _build_world_map_cache(self, width: int, height: int):
        """Render a legible static M-map layer once for the current map/window.

        Road labels are optional annotations, not geometry. Long source names
        names are abbreviated, duplicate names are collapsed, and every label is
        collision-tested before drawing. This prevents the unreadable stacks of
        road names used in the early GWB prototype.
        """
        width = max(64, int(width))
        height = max(64, int(height))
        world_w = max(1.0, float(self.map_config.get("world_w", 1)))
        world_h = max(1.0, float(self.map_config.get("world_h", 1)))
        scale = min(width / world_w, height / world_h)
        draw_w = max(1, min(width, int(round(world_w * scale))))
        draw_h = max(1, min(height, int(round(world_h * scale))))
        surface = pygame.Surface((draw_w, draw_h)).convert()
        surface.fill((68, 75, 67))

        sx = draw_w / world_w
        sy = draw_h / world_h

        def mp(point):
            safe = self._safe_map_point(point, world_w, world_h)
            if safe is None:
                return None
            return (
                max(0, min(draw_w - 1, int(round(safe[0] * sx)))),
                max(0, min(draw_h - 1, int(round(safe[1] * sy)))),
            )

        def short_label(raw: str) -> str:
            name = str(raw or "").encode("ascii", "replace").decode("ascii").strip()
            replacements = (
                ("George Washington Bridge", "GWB"),
                ("Trans-Manhattan Expressway", "Trans-Manhattan Expy"),
                ("New Jersey Turnpike Local Roadway", "NJ Turnpike Local"),
                ("New Jersey Turnpike", "NJ Turnpike"),
                ("Palisades Interstate Parkway", "Palisades Pkwy"),
                ("Henry Hudson Parkway", "Henry Hudson Pkwy"),
                ("Major Deegan Expressway", "Major Deegan Expy"),
                ("Robert F. Kennedy Bridge", "RFK Bridge"),
                ("Expressway", "Expy"),
                ("Parkway", "Pkwy"),
                ("Boulevard", "Blvd"),
                ("Avenue", "Ave"),
                ("Roadway", "Rdwy"),
                ("Street", "St"),
            )
            for old, rep in replacements:
                name = name.replace(old, rep)
            name = " ".join(name.split())
            if len(name) > 27:
                name = name[:26].rstrip() + "…"
            return name

        occupied: list[pygame.Rect] = []

        def place_label(text: str, anchors, color, *, dark_back: bool = True) -> bool:
            text = short_label(text)
            if not text:
                return False
            label = self.tiny_font.render(text, True, color)
            lw, lh = label.get_size()
            if lw >= draw_w - 4 or lh >= draw_h - 4:
                return False
            for ax, ay in anchors:
                placements = (
                    (ax + 5, ay - lh - 4),
                    (ax + 5, ay + 4),
                    (ax - lw - 5, ay - lh - 4),
                    (ax - lw - 5, ay + 4),
                )
                for lx, ly in placements:
                    rect = pygame.Rect(int(lx) - 2, int(ly) - 1, lw + 4, lh + 2)
                    if rect.left < 1 or rect.top < 1 or rect.right >= draw_w - 1 or rect.bottom >= draw_h - 1:
                        continue
                    padded = rect.inflate(8, 5)
                    if any(padded.colliderect(other) for other in occupied):
                        continue
                    if dark_back:
                        pygame.draw.rect(surface, (32, 35, 34), rect, border_radius=2)
                    surface.blit(label, (rect.x + 2, rect.y + 1))
                    occupied.append(rect)
                    return True
            return False

        for poly in self.map_config.get("water_polygons", []) or []:
            points = [q for q in (mp(p) for p in (poly or [])) if q is not None]
            if len(points) >= 3:
                pygame.draw.polygon(surface, (38, 61, 74), points)

        road_label_candidates = []
        for road in self.map_config.get("roads", []) or []:
            points = [q for q in (mp(p) for p in (road.get("points", []) or [])) if q is not None]
            if len(points) < 2:
                continue
            try:
                road_world_width = max(1.0, float(road.get("width", 80)))
            except (TypeError, ValueError):
                road_world_width = 80.0
            line_width = max(1, min(12, int(round(road_world_width * min(sx, sy)))))
            color = (210, 188, 96) if road.get("bridge") else (150, 151, 142)
            pygame.draw.lines(surface, color, False, points, line_width)
            if road.get("map_label"):
                # Try multiple points along the road rather than forcing every
                # label into a single midpoint where major approaches converge.
                indices = sorted(set((len(points) // 4, len(points) // 2, (len(points) * 3) // 4)))
                anchors = [points[min(len(points) - 1, i)] for i in indices]
                road_label_candidates.append((road_world_width, str(road.get("name", "")), anchors))

        # Boundary portals remain readable on the regional map as short dark
        # cross-road bars. Their roads still stop at the authoritative world wall.
        for prop in self.map_config.get("street_props", []) or []:
            if str(prop.get("kind", "")) != "edge_tunnel":
                continue
            p = mp(prop.get("pos", [0, 0]))
            if p is None:
                continue
            angle = math.radians(float(prop.get("rotation", 0.0)))
            nx, ny = -math.sin(angle), math.cos(angle)
            half = max(3, min(9, int(round(float(prop.get("scale", 1.0)) * 3.0))))
            a = (int(p[0] - nx * half), int(p[1] - ny * half))
            b = (int(p[0] + nx * half), int(p[1] + ny * half))
            pygame.draw.line(surface, (8, 10, 11), a, b, 4)
            pygame.draw.line(surface, (205, 176, 68), a, b, 1)

        for lane in self.map_config.get("bike_lanes", []) or []:
            points = [q for q in (mp(p) for p in (lane.get("points", []) or [])) if q is not None]
            if len(points) >= 2:
                pygame.draw.lines(surface, (88, 148, 94), False, points, max(1, min(4, int(round(12 * min(sx, sy))))))

        # Landmarks and districts take label priority over roads.
        for landmark in self.map_config.get("landmarks", []) or []:
            p = mp(landmark.get("pos", [0, 0]))
            if p is None:
                continue
            kind = str(landmark.get("kind", "landmark"))
            color = (237, 207, 89) if kind in {"bridge", "landmark"} else (222, 224, 218)
            pygame.draw.circle(surface, (11, 12, 12), p, 4)
            pygame.draw.circle(surface, color, p, 2)
            place_label(str(landmark.get("name", "")), [p], TEXT_COLOR)

        for district in self.map_config.get("districts", []) or []:
            p = mp(district.get("pos", [0, 0]))
            if p is None:
                continue
            name = short_label(str(district.get("name", "")))
            if not name:
                continue
            text = self.tiny_font.render(name, True, (183, 188, 183))
            rect = text.get_rect(center=p).inflate(6, 4)
            if rect.left >= 1 and rect.top >= 1 and rect.right < draw_w - 1 and rect.bottom < draw_h - 1 and not any(rect.inflate(5, 3).colliderect(o) for o in occupied):
                surface.blit(text, text.get_rect(center=p))
                occupied.append(rect)

        # One label per normalized road name, widest/most-important roads first.
        seen_names = set()
        label_count = 0
        for road_width, name, anchors in sorted(road_label_candidates, key=lambda row: row[0], reverse=True):
            normalized = short_label(name).casefold()
            if not normalized or normalized in seen_names:
                continue
            seen_names.add(normalized)
            # On a regional map, minor road names create more noise than value.
            if road_width < 58 and label_count >= 8:
                continue
            if place_label(name, anchors, (205, 207, 200)):
                label_count += 1
            if label_count >= 16:
                break

        # Human-readable A1/B2/... chunk reference grid. The grid is north-up
        # and uses exactly the same 1024 px chunks as streaming/compiler output.
        chunk_size = max(1, int(self.map_config.get("chunk_size", 1024)))
        chunk_cols = max(1, int(self.map_config.get("chunk_cols", math.ceil(world_w / chunk_size))))
        chunk_rows = max(1, int(self.map_config.get("chunk_rows", math.ceil(world_h / chunk_size))))
        grid_color = (96, 101, 96)
        grid_text = (214, 216, 208)
        for gx in range(1, chunk_cols):
            px = int(round(gx * chunk_size * sx))
            if 0 < px < draw_w:
                pygame.draw.line(surface, grid_color, (px, 0), (px, draw_h - 1), 1)
        for gy in range(1, chunk_rows):
            py = int(round(gy * chunk_size * sy))
            if 0 < py < draw_h:
                pygame.draw.line(surface, grid_color, (0, py), (draw_w - 1, py), 1)
        for gy in range(chunk_rows):
            for gx in range(chunk_cols):
                x0 = gx * chunk_size * sx
                x1 = min(world_w, (gx + 1) * chunk_size) * sx
                y0 = gy * chunk_size * sy
                y1 = min(world_h, (gy + 1) * chunk_size) * sy
                if x1 - x0 < 18 or y1 - y0 < 14:
                    continue
                label = self.tiny_font.render(chunk_label(gx, gy), True, grid_text)
                badge = label.get_rect(center=(int((x0+x1)*0.5), int((y0+y1)*0.5)))
                back = badge.inflate(4, 2)
                pygame.draw.rect(surface, (30, 33, 32), back, border_radius=2)
                surface.blit(label, badge)

        pygame.draw.rect(surface, (108, 111, 104), surface.get_rect(), width=1)
        return surface, world_w, world_h

    def _draw_world_map_impl(self) -> None:
        sw, sh = self.screen.get_size()
        if sw < 220 or sh < 180:
            # Still produce a valid overlay on tiny resized windows.
            msg = self.small_font.render("Window too small for world map - resize or press M", True, TEXT_COLOR)
            self.screen.blit(msg, (10, 10))
            return

        shade = pygame.Surface((sw, sh), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 205))
        self.screen.blit(shade, (0, 0))

        margin_x = min(42, max(10, sw // 20))
        margin_y = min(38, max(10, sh // 20))
        panel = pygame.Rect(margin_x, margin_y, max(200, sw - 2 * margin_x), max(160, sh - 2 * margin_y))
        panel.clamp_ip(self.screen.get_rect())
        pygame.draw.rect(self.screen, (20, 23, 24), panel, border_radius=9)
        pygame.draw.rect(self.screen, (88, 92, 93), panel, width=2, border_radius=9)
        title_text = str(self.map_config.get("name", "WORLD MAP")).upper()
        title = self.big_font.render(title_text, True, TEXT_COLOR)
        self.screen.blit(title, (panel.x + 18, panel.y + 12))
        subtitle = self.small_font.render("M close | WASD still moves | yellow: you | blue: all online players", True, MUTED_TEXT)
        self.screen.blit(subtitle, (panel.x + 20, panel.y + 46))

        available = pygame.Rect(panel.x + 20, panel.y + 72, max(64, panel.width - 40), max(64, panel.height - 102))
        cache_key = (
            str(self.map_config.get("id", "")),
            int(self.map_config.get("world_w", 1)),
            int(self.map_config.get("world_h", 1)),
            available.width, available.height,
        )
        if self._world_map_cache is None or self._world_map_cache_key != cache_key:
            self._world_map_cache = self._build_world_map_cache(available.width, available.height)
            self._world_map_cache_key = cache_key

        map_surface, world_w, world_h = self._world_map_cache
        map_rect = map_surface.get_rect(center=available.center)
        self.screen.blit(map_surface, map_rect)
        sx = map_rect.width / max(1.0, world_w)
        sy = map_rect.height / max(1.0, world_h)

        def mp_dynamic(x, y):
            try:
                x = max(0.0, min(world_w, float(x)))
                y = max(0.0, min(world_h, float(y)))
            except (TypeError, ValueError):
                return None
            if not (math.isfinite(x) and math.isfinite(y)):
                return None
            return int(map_rect.x + x * sx), int(map_rect.y + y * sy)

        local = self.players.get(self.local_id or "")
        if local is not None:
            p = mp_dynamic(local.render_x, local.render_y)
            if p is not None:
                pygame.draw.circle(self.screen, (12, 13, 13), p, 7)
                pygame.draw.circle(self.screen, LOCAL_COLOR, p, 5)

            chunk_size = max(1, int(self.map_config.get("chunk_size", 1024)))
            cx, cy = world_to_chunk(local.render_x, local.render_y, self.map_config)
            chunk_rect = pygame.Rect(
                int(map_rect.x + cx * chunk_size * sx),
                int(map_rect.y + cy * chunk_size * sy),
                max(1, int(math.ceil(chunk_size * sx))),
                max(1, int(math.ceil(chunk_size * sy))),
            ).clip(map_rect)
            if chunk_rect.width > 0 and chunk_rect.height > 0:
                pygame.draw.rect(self.screen, LOCAL_COLOR, chunk_rect, width=1)

            r = max(0, min(12, int(self.interest_radius)))
            ix0 = max(0, cx - r) * chunk_size
            iy0 = max(0, cy - r) * chunk_size
            ix1 = min(world_w, (cx + r + 1) * chunk_size)
            iy1 = min(world_h, (cy + r + 1) * chunk_size)
            interest_rect = pygame.Rect(
                int(map_rect.x + ix0 * sx), int(map_rect.y + iy0 * sy),
                max(1, int((ix1 - ix0) * sx)), max(1, int((iy1 - iy0) * sy)),
            ).clip(map_rect)
            if interest_rect.width > 0 and interest_rect.height > 0:
                pygame.draw.rect(self.screen, (116, 164, 186), interest_rect, width=1)

        for pid, marker in self.map_players.items():
            if pid == self.local_id:
                continue
            live = self.players.get(pid)
            px = live.render_x if live is not None else marker.get("x", 0.0)
            py = live.render_y if live is not None else marker.get("y", 0.0)
            p = mp_dynamic(px, py)
            if p is not None and map_rect.collidepoint(p):
                pygame.draw.circle(self.screen, (12, 13, 13), p, 6)
                pygame.draw.circle(self.screen, REMOTE_COLOR, p, 4)
                name = str(marker.get("name", "Player"))[:18]
                level = int(marker.get("level", 0) or 0)
                label_text = f"{name} L{level}" if level else name
                label = self.tiny_font.render(label_text, True, (176, 215, 232))
                label_rect = label.get_rect(midleft=(p[0] + 7, p[1]))
                pygame.draw.rect(self.screen, (18, 21, 22), label_rect.inflate(4, 2), border_radius=2)
                self.screen.blit(label, label_rect)

        try:
            cx, cy = int(self.server_chunk[0]), int(self.server_chunk[1])
        except (TypeError, ValueError, IndexError):
            cx, cy = 0, 0
        chunk_size = max(1, int(self.map_config.get("chunk_size", 1024)))
        cols = max(1, int(self.map_config.get("chunk_cols", math.ceil(world_w / chunk_size))))
        rows = max(1, int(self.map_config.get("chunk_rows", math.ceil(world_h / chunk_size))))
        status = self.small_font.render(
            f"Chunk {chunk_label(cx, cy)} ({cx},{cy}) of {cols}x{rows} | streamed radius {int(self.interest_radius)}",
            True, TEXT_COLOR,
        )
        self.screen.blit(status, (panel.x + 20, panel.bottom - 24))

    def draw_world_map(self) -> None:
        if not self.map_open:
            return
        try:
            self._draw_world_map_impl()
            self._world_map_last_error = ""
        except Exception as exc:
            # The world map is optional UI. Never allow it to terminate gameplay.
            self._world_map_last_error = f"{type(exc).__name__}: {exc}"
            print("WORLD MAP RENDER ERROR:", self._world_map_last_error)
            traceback.print_exc()
            self.map_open = False
            self.notice = "World map could not render; gameplay continued. See console for details."
            self.notice_until = time.monotonic() + 6.0

    def draw_vehicle(self, car: RemoteVehicle) -> None:
        sx, sy = self.world_to_screen(car.render_x, car.render_y)
        target_len = int(max(62, car.render_length * 1.38))
        if draw_car(self.screen, (sx, sy), car.angle, car.sprite_index, target_length=target_len, speed=car.speed):
            return
        length = max(24, int(car.collision_length))
        width = max(14, int(car.collision_width))
        sprite = pygame.Surface((length + 8, width + 8), pygame.SRCALPHA)
        body = pygame.Rect(4, 4, length, width)
        color = tuple(TRAFFIC_CAR_COLORS[car.color_index % len(TRAFFIC_CAR_COLORS)])
        pygame.draw.rect(sprite, (12, 13, 13, 110), body.move(2, 3), border_radius=4)
        pygame.draw.rect(sprite, color, body, border_radius=4)
        pygame.draw.rect(sprite, (31, 34, 36), body, width=2, border_radius=4)
        cabin = pygame.Rect(body.x + 9, body.y + 3, 15, body.height - 6)
        pygame.draw.rect(sprite, (49, 67, 72), cabin, border_radius=3)
        pygame.draw.line(sprite, (104, 127, 130), (cabin.centerx, cabin.top + 1), (cabin.centerx, cabin.bottom - 1), 1)
        # Front is +X before rotation.
        pygame.draw.circle(sprite, (235, 224, 156), (body.right - 2, body.top + 4), 2)
        pygame.draw.circle(sprite, (235, 224, 156), (body.right - 2, body.bottom - 4), 2)
        pygame.draw.circle(sprite, (184, 48, 43), (body.left + 2, body.top + 4), 2)
        pygame.draw.circle(sprite, (184, 48, 43), (body.left + 2, body.bottom - 4), 2)
        angle_deg = -math.degrees(car.angle)
        quarter_turn = abs((angle_deg / 90.0) - round(angle_deg / 90.0)) < 1e-4
        rotated = pygame.transform.rotate(sprite, angle_deg) if quarter_turn else pygame.transform.rotozoom(sprite, angle_deg, 1.0)
        self.screen.blit(rotated, rotated.get_rect(center=(sx, sy)))

    def draw_bicycle_entity(self, bike: RemoteBicycle) -> None:
        sx, sy = self.world_to_screen(bike.render_x, bike.render_y)
        rider_appearance = None
        local_ring = None
        if bike.rider == "player" and bike.controlled_by:
            rider_player = self.players.get(bike.controlled_by)
            if rider_player is not None:
                rider_appearance = rider_player.appearance
        elif bike.rider == "npc":
            rider_appearance = bike.appearance
        draw_bicycle(
            self.screen, (sx, sy), bike.angle,
            color_index=sum(ord(c) for c in bike.id) % 7,
            rider_appearance=rider_appearance,
            moving=abs(bike.speed) > 3.0,
            anim_time=time.monotonic() - bike.anim_epoch,
            local_ring=local_ring,
            rider_scale=max(1, int(self.settings.get("render", {}).get("cyclist_rider_scale", 2))),
            bike_scale=max(0.25, float(self.map_config.get("bicycle_render_scale", 2.0))),
        )

    def draw_npc(self, npc: RemoteNPC) -> None:
        sx, sy = self.world_to_screen(npc.render_x, npc.render_y)
        npc_scale = max(1, int(self.settings.get("render", {}).get("npc_scale", 2)))
        draw_character(
            self.screen, (sx, sy), npc.aim, npc.appearance, scale=npc_scale,
            moving=time.monotonic() < npc.moving_until,
            anim_time=time.monotonic() - npc.anim_epoch,
        )

    def nearest_client_bicycle(self, radius: float = 96.0) -> RemoteBicycle | None:
        local = self.players.get(self.local_id or "")
        if local is None:
            return None
        best = None
        best_d = float(radius)
        for bike in self.bicycles.values():
            d = math.hypot(bike.render_x - local.render_x, bike.render_y - local.render_y)
            if d <= best_d:
                best, best_d = bike, d
        return best

    def nearest_client_vehicle(self, radius: float = 118.0) -> RemoteVehicle | None:
        local = self.players.get(self.local_id or "")
        if local is None:
            return None
        best = None
        best_d = float(radius)
        for car in self.vehicles.values():
            d = math.hypot(car.render_x - local.render_x, car.render_y - local.render_y)
            if d <= best_d:
                best, best_d = car, d
        return best

    def draw_vehicle_status(self) -> None:
        local = self.players.get(self.local_id or "")
        if local is None or self.interior.active or self.inventory_open or self.map_open:
            return
        w, h = self.screen.get_size()
        if getattr(local, "in_vehicle", False):
            kind = getattr(local, "vehicle_kind", "")
            if kind == "bicycle":
                bike = self.bicycles.get(getattr(local, "vehicle_id", ""))
                if bike is not None:
                    mph = int(abs(bike.speed) * 0.18)
                    text = self.font.render(f"BICYCLE   {mph:02d} mph   [T] DISMOUNT", True, TEXT_COLOR)
                    box = text.get_rect(midbottom=(w // 2, h - 18)).inflate(22, 12)
                    pygame.draw.rect(self.screen, (18,20,21), box, border_radius=5)
                    pygame.draw.rect(self.screen, (84,136,92), box, width=1, border_radius=5)
                    self.screen.blit(text, text.get_rect(center=box.center))
                return
            car = self.vehicles.get(getattr(local, "vehicle_id", ""))
            if car is not None:
                mph = int(abs(car.speed) * 0.18)
                role = str(getattr(local, "vehicle_role", "driver"))
                if role == "passenger":
                    caption = f"PASSENGER   {car.vehicle_class.upper()}   {mph:02d} mph   [T] EXIT"
                else:
                    caption = f"DRIVER   {car.vehicle_class.upper()}   {mph:02d} mph   [SHIFT] BOOST   [T] EXIT"
                text = self.font.render(caption, True, TEXT_COLOR)
                box = text.get_rect(midbottom=(w // 2, h - 18)).inflate(22, 12)
                pygame.draw.rect(self.screen, (18,20,21), box, border_radius=5)
                pygame.draw.rect(self.screen, (100,104,104), box, width=1, border_radius=5)
                self.screen.blit(text, text.get_rect(center=box.center))
            return

        car = self.nearest_client_vehicle()
        bike = self.nearest_client_bicycle()
        car_d = math.hypot(car.render_x-local.render_x, car.render_y-local.render_y) if car else float("inf")
        bike_d = math.hypot(bike.render_x-local.render_x, bike.render_y-local.render_y) if bike else float("inf")
        if bike is not None and bike_d <= car_d:
            action = "TAKE" if bike.rider == "npc" else "RIDE"
            text = self.font.render(f"[T] {action} BICYCLE", True, (108, 202, 126))
        elif car is not None:
            if car.driver == "player":
                action = "RIDE AS PASSENGER" if car.passengers < car.passenger_capacity else "CAR FULL"
            else:
                action = "STEAL" if car.driver == "npc" else "ENTER"
            text = self.font.render(f"[T] {action} {car.vehicle_class.upper()}", True, LOCAL_COLOR)
        else:
            return
        box = text.get_rect(midbottom=(w // 2, h - 18)).inflate(22, 12)
        pygame.draw.rect(self.screen, (18,20,21), box, border_radius=5)
        pygame.draw.rect(self.screen, (120,111,63), box, width=1, border_radius=5)
        self.screen.blit(text, text.get_rect(center=box.center))

    def draw_location(self, pos, color, label: str, sublabel: str) -> None:
        sx, sy = self.world_to_screen(*pos)
        pygame.draw.circle(self.screen, color, (sx, sy), 34, width=4)
        pygame.draw.circle(self.screen, color, (sx, sy), 8)
        self.screen.blit(self.small_font.render(label, True, TEXT_COLOR), self.small_font.render(label, True, TEXT_COLOR).get_rect(center=(sx, sy - 52)))
        sub = self.small_font.render(sublabel, True, TEXT_COLOR)
        self.screen.blit(sub, sub.get_rect(center=(sx, sy + 52)))

    def draw_player(self, player: RemotePlayer, local: bool) -> None:
        sx, sy = self.world_to_screen(player.render_x, player.render_y)
        if getattr(player, "in_vehicle", False) or getattr(player, "interior_id", ""):
            return
        player_scale = max(1, int(self.settings.get("render", {}).get("player_scale", 2)))
        moving = time.monotonic() < player.moving_until

        # Body orientation is independent of mouse aim. While moving it follows
        # the actual authoritative movement heading. When local movement stops,
        # the body settles to the camera-facing idle pose without changing any
        # movement vector. Remote idle bodies simply retain their last heading.
        body_aim = float(getattr(player, "move_heading", player.aim))
        if local and self.camera_rotation_dragging:
            # Middle-mouse rotation is an explicit camera+avatar presentation
            # gesture: keep the player's front locked to screen/camera forward
            # even if the movement interpolation window is still active.
            body_aim = math.radians(self.camera_rotation_degrees) - math.pi * 0.5
        elif local and not moving and bool(self.settings.get("controls", {}).get("idle_body_realign_camera", True)):
            body_aim = math.radians(self.camera_rotation_degrees) - math.pi * 0.5

        pose = str(getattr(player, "pose", "idle"))
        animation = pose if pose in {"jump", "crouch", "run"} else ("walk" if moving else "idle")
        render_scale = float(player_scale)
        if animation == "jump":
            render_scale *= max(1.0, float(self.settings.get("render", {}).get("jump_scale_multiplier", 1.35)))
            sy -= int(round(float(self.settings.get("render", {}).get("jump_lift_px", 10))))
        draw_character(
            self.screen, (sx, sy), body_aim, player.appearance, scale=render_scale, local_ring=None,
            moving=moving, animation=animation, anim_time=time.monotonic() - player.anim_epoch,
        )

    def draw_blood_stain(self, stain: dict) -> None:
        try:
            sx, sy = self.world_to_screen(float(stain.get("x", 0.0)), float(stain.get("y", 0.0)))
            remaining = max(0.0, float(stain.get("remaining", 0.0)))
        except (TypeError, ValueError):
            return
        fade = max(0.25, min(1.0, remaining / 3.0))
        color = (int(132 * fade), int(22 * fade), int(27 * fade))
        pygame.draw.ellipse(self.screen, color, pygame.Rect(sx - 17, sy - 8, 34, 16))
        pygame.draw.circle(self.screen, (max(35, color[0] - 22), 12, 15), (sx + 12, sy + 4), 6)
        pygame.draw.circle(self.screen, (max(28, color[0] - 35), 10, 12), (sx - 13, sy - 2), 5)

    def _world_point_to_display(self, x: float, y: float) -> tuple[int, int]:
        """Transform one world point through the same camera rotation/zoom as the scene."""
        z = max(0.05, float(self.camera_zoom))
        vw, vh = self.logical_view_size()
        rotation_active = self.camera_rotation_enabled and abs(self.camera_rotation_degrees % 360.0) > 0.01
        if rotation_active:
            local = self.players.get(self.local_id or "")
            if local is not None:
                cx, cy = float(local.render_x), float(local.render_y)
            else:
                cx, cy = self.camera_controller.center((vw, vh))
            dx, dy = float(x) - cx, float(y) - cy
            theta = math.radians(self.camera_rotation_degrees)
            c, sn = math.cos(theta), math.sin(theta)
            # Match pygame.transform.rotate's positive visual rotation in screen coordinates.
            rx = c * dx + sn * dy
            ry = -sn * dx + c * dy
            lx, ly = vw * 0.5 + rx, vh * 0.5 + ry
        else:
            cam_x, cam_y = self.camera()
            lx, ly = float(x) - cam_x, float(y) - cam_y
        return int(round(lx * z)), int(round(ly * z))

    def draw_player_nameplates(self) -> None:
        """Draw names in final screen space so camera rotation never tilts text."""
        for player in self.players.values():
            if getattr(player, "interior_id", ""):
                continue
            in_vehicle = bool(getattr(player, "in_vehicle", False))
            if in_vehicle:
                vehicle_id = str(getattr(player, "vehicle_id", ""))
                vehicle = self.vehicles.get(vehicle_id)
                px = vehicle.render_x if vehicle is not None else player.render_x
                py = vehicle.render_y if vehicle is not None else player.render_y
                occupants = sorted(
                    (other for other in self.players.values()
                     if bool(getattr(other, "in_vehicle", False))
                     and str(getattr(other, "vehicle_id", "")) == vehicle_id),
                    key=lambda other: (0 if getattr(other, "vehicle_role", "") == "driver" else 1, other.name, other.id),
                )
                row = next((i for i, other in enumerate(occupants) if other.id == player.id), 0)
            else:
                px, py, row = player.render_x, player.render_y, 0
            sx, sy = self._world_point_to_display(px, py)
            player_scale = max(1, int(self.settings.get("render", {}).get("player_scale", 2)))
            yoff = int((19 + 15 * player_scale) * max(0.75, float(self.camera_zoom)))
            if in_vehicle:
                yoff += row * max(15, self.small_font.get_linesize())
            elif str(getattr(player, "pose", "idle")) == "jump":
                yoff += int(round(float(self.settings.get("render", {}).get("jump_lift_px", 10))))
            name_color = LOCAL_COLOR if player.id == self.local_id else REMOTE_COLOR
            name = self.small_font.render(player.name, True, name_color)
            nr = name.get_rect(midbottom=(sx, sy - yoff))
            self.screen.blit(self.small_font.render(player.name, True, SHADOW), nr.move(1, 1))
            self.screen.blit(name, nr)
            bubble = self.chat_bubbles.get(player.id)
            if bubble and time.monotonic() < float(bubble.get("until", 0.0)):
                self.draw_chat_bubble(sx, nr.top - 8, str(bubble.get("text", "")), str(bubble.get("scope", "local")))

    def draw_chat_bubble(self, anchor_x: int, anchor_y: int, text: str, scope: str = "local") -> None:
        words = str(text).split()
        lines: list[str] = []
        current = ""
        for word in words:
            trial = f"{current} {word}".strip()
            if current and self.small_font.size(trial)[0] > 260:
                lines.append(current)
                current = word
            else:
                current = trial
        if current:
            lines.append(current)
        lines = lines[:3] or [""]
        width = min(280, max(54, max(self.small_font.size(line)[0] for line in lines) + 22))
        height = 14 + len(lines) * self.small_font.get_linesize()
        rect = pygame.Rect(0, 0, width, height)
        rect.midbottom = (int(anchor_x), int(anchor_y) - 8)
        rect.clamp_ip(self.screen.get_rect().inflate(-8, -8))
        edge = (190, 125, 235) if scope == "whisper" else (92, 99, 102)
        pygame.draw.rect(self.screen, (245, 244, 235), rect, border_radius=7)
        pygame.draw.rect(self.screen, edge, rect, width=2, border_radius=7)
        tip_x = max(rect.left + 12, min(rect.right - 12, anchor_x))
        pygame.draw.polygon(self.screen, (245, 244, 235), [(tip_x - 6, rect.bottom - 1), (tip_x + 6, rect.bottom - 1), (anchor_x, anchor_y)])
        for i, line in enumerate(lines):
            self.screen.blit(self.small_font.render(line, True, (27, 28, 29)), (rect.x + 11, rect.y + 7 + i * self.small_font.get_linesize()))

    def draw_chat_input(self) -> None:
        if not self.chat_active:
            return
        w, h = self.screen.get_size()
        rect = pygame.Rect(max(18, w // 2 - 360), h - 66, min(720, w - 36), 44)
        pygame.draw.rect(self.screen, (17, 19, 20), rect, border_radius=6)
        pygame.draw.rect(self.screen, REMOTE_COLOR, rect, width=2, border_radius=6)
        prompt = self.chat_text + ("_" if int(time.monotonic() * 2) % 2 == 0 else "")
        shown = self.font.render(prompt[-90:], True, TEXT_COLOR)
        self.screen.blit(shown, (rect.x + 14, rect.y + 11))
        hint = self.tiny_font.render("ENTER send   /bug description   /w FriendName message   ESC cancel", True, MUTED_TEXT)
        self.screen.blit(hint, (rect.x + 8, rect.y - 18))

    def inventory_geometry(self) -> tuple[pygame.Rect, list[pygame.Rect]]:
        w, h = self.screen.get_size()
        slot = max(62, min(92, (min(w - 180, 570) - 52) // INVENTORY_COLS))
        gap = 8
        grid_w = INVENTORY_COLS * slot + (INVENTORY_COLS - 1) * gap
        grid_h = INVENTORY_ROWS * slot + (INVENTORY_ROWS - 1) * gap
        panel_w = grid_w + 64
        panel_h = grid_h + 190
        panel = pygame.Rect((w - panel_w) // 2, max(24, (h - panel_h) // 2), panel_w, panel_h)
        start_x, start_y = panel.x + 32, panel.y + 78
        slots = []
        for row in range(INVENTORY_ROWS):
            for col in range(INVENTORY_COLS):
                slots.append(pygame.Rect(start_x + col * (slot + gap), start_y + row * (slot + gap), slot, slot))
        return panel, slots

    def draw_item_icon(self, rect: pygame.Rect, item_id: str) -> None:
        item = ITEM_DEFS.get(item_id, {})
        color = tuple(item.get("ui_color", [130, 130, 130]))
        # Stylized parcel icon, deliberately asset-free for the prototype.
        box = rect.inflate(-rect.width // 3, -rect.height // 3)
        pygame.draw.rect(self.screen, color, box, border_radius=4)
        pygame.draw.rect(self.screen, (75, 65, 45), box, width=2, border_radius=4)
        pygame.draw.line(self.screen, (220, 205, 150), (box.centerx, box.top + 2), (box.centerx, box.bottom - 2), 2)
        pygame.draw.line(self.screen, (220, 205, 150), (box.left + 3, box.centery), (box.right - 3, box.centery), 2)

    def draw_inventory(self) -> None:
        if not self.inventory_open:
            return
        w, h = self.screen.get_size()
        shade = pygame.Surface((w, h), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 155))
        self.screen.blit(shade, (0, 0))
        panel, slot_rects = self.inventory_geometry()
        pygame.draw.rect(self.screen, INV_PANEL, panel, border_radius=10)
        pygame.draw.rect(self.screen, (72, 75, 76), panel, width=2, border_radius=10)
        self.screen.blit(self.inv_title_font.render("INVENTORY", True, TEXT_COLOR), (panel.x + 32, panel.y + 24))
        if self.account_masked:
            acct = self.small_font.render(f"ACCOUNT {self.account_masked}", True, MUTED_TEXT)
            self.screen.blit(acct, (panel.right - acct.get_width() - 32, panel.y + 32))

        for index, rect in enumerate(slot_rects):
            selected = index == self.selected_slot
            pygame.draw.rect(self.screen, INV_SLOT, rect, border_radius=4)
            pygame.draw.rect(self.screen, INV_SELECTED if selected else INV_SLOT_EDGE, rect, width=3 if selected else 2, border_radius=4)
            slot = self.inventory[index] if index < len(self.inventory) else None
            if slot:
                item_id = str(slot["item_id"])
                self.draw_item_icon(rect, item_id)
                qty = int(slot.get("quantity", 0))
                if qty > 1:
                    badge = pygame.Rect(rect.right - 28, rect.bottom - 25, 23, 20)
                    pygame.draw.rect(self.screen, (11, 12, 12), badge, border_radius=8)
                    q = self.tiny_font.render(str(qty), True, TEXT_COLOR)
                    self.screen.blit(q, q.get_rect(center=badge.center))

        current_weight = inventory_weight(self.inventory)
        footer_y = slot_rects[-1].bottom + 18
        self.screen.blit(self.font.render(f"WEIGHT  {current_weight:.1f} / {INVENTORY_MAX_WEIGHT_KG:.1f} kg", True, TEXT_COLOR), (panel.x + 32, footer_y))
        selected = self.inventory[self.selected_slot] if 0 <= self.selected_slot < len(self.inventory) else None
        if selected:
            item = ITEM_DEFS.get(str(selected["item_id"]), {})
            desc = f'{item.get("name", selected["item_id"])}  x{selected.get("quantity", 0)}  •  {float(item.get("weight_kg", 0)):.2f} kg each'
        else:
            desc = "Empty slot"
        self.screen.blit(self.small_font.render(desc, True, MUTED_TEXT), (panel.x + 32, footer_y + 34))
        hint = self.small_font.render("I / TAB close    click/select    drag items between slots", True, (125, 128, 130))
        self.screen.blit(hint, (panel.x + 32, panel.bottom - 28))

    def inventory_slot_at(self, pos: tuple[int, int]) -> int | None:
        _, slot_rects = self.inventory_geometry()
        for index, rect in enumerate(slot_rects):
            if rect.collidepoint(pos):
                return index
        return None

    def reload_visual_style(self, *, manual: bool = False) -> None:
        style = apply_client_art_style()
        self.art_style = style
        reload_character_style()
        reload_vehicle_style()
        self.environment.reload_style()
        self.settings = load_settings()
        self.camera_controller.tuning = dict(self.settings.get("camera", {}))
        cam_cfg = self.settings.get("camera", {})
        self.camera_zoom_min = float(cam_cfg.get("zoom_min", getattr(self, "camera_zoom_min", 0.55)))
        self.camera_zoom_max = float(cam_cfg.get("zoom_max", getattr(self, "camera_zoom_max", 2.0)))
        self.camera_zoom_step = float(cam_cfg.get("zoom_step", getattr(self, "camera_zoom_step", 0.10)))
        self.camera_zoom = max(self.camera_zoom_min, min(self.camera_zoom_max, getattr(self, "camera_zoom", 1.0)))
        self.camera_rotation_enabled = bool(cam_cfg.get("rotation_enabled", getattr(self, "camera_rotation_enabled", True)))
        self.camera_rotation_sensitivity = float(cam_cfg.get("rotation_sensitivity_deg_per_px", getattr(self, "camera_rotation_sensitivity", 0.32)))
        self.camera_rotation_snap = max(0.0, float(cam_cfg.get("rotation_snap_degrees", getattr(self, "camera_rotation_snap", 0.0))))
        self.camera_center_player_when_rotated = bool(cam_cfg.get("center_player_when_rotated", getattr(self, "camera_center_player_when_rotated", True)))
        hot = style.get("hot_reload", {})
        self.hot_reload_enabled = bool(hot.get("enabled", self.hot_reload_enabled))
        self.hot_reload_poll_seconds = float(hot.get("poll_seconds", self.hot_reload_poll_seconds))
        self._world_map_cache = None
        self._world_map_cache_key = None
        self.style_watcher.reset()
        self.settings_watcher.reset()
        self.notice = "Art/settings reloaded" if manual else "Art/settings hot-reloaded"
        self.notice_until = time.monotonic() + 2.0

    def poll_hot_reload(self) -> None:
        if not self.hot_reload_enabled:
            return
        if self.style_watcher.changed(self.hot_reload_poll_seconds) or self.settings_watcher.changed(self.hot_reload_poll_seconds):
            self.reload_visual_style(manual=False)

    def manual_chunk_reload(self, mode: str) -> None:
        cx, cy = self.server_chunk
        if mode == "current":
            self.environment.invalidate_chunk(cx, cy)
            text = f"Rebuilt chunk {chunk_label(cx, cy)} ({cx},{cy})"
        elif mode == "near":
            self.environment.invalidate_near(cx, cy, radius=1)
            text = "Rebuilt nearby 3x3 chunks"
        else:
            self.environment.invalidate_all()
            text = "Cleared all rendered chunk cache"
        self.notice = text
        self.notice_until = time.monotonic() + 2.0

    def _pause_layout(self):
        sw, sh = self.screen.get_size()
        pw = min(820, max(620, sw - 100))
        ph = min(620, max(500, sh - 70))
        panel = pygame.Rect((sw - pw)//2, (sh - ph)//2, pw, ph)
        buttons = {
            "resume": pygame.Rect(panel.x + 24, panel.bottom - 64, 130, 40),
            "settings": pygame.Rect(panel.x + 166, panel.bottom - 64, 130, 40),
            "friends": pygame.Rect(panel.x + 308, panel.bottom - 64, 130, 40),
            "quit": pygame.Rect(panel.right - 154, panel.bottom - 64, 130, 40),
            "back": pygame.Rect(panel.x + 24, panel.bottom - 64, 130, 40),
        }
        toggles = {
            key: pygame.Rect(panel.right - 210, panel.y + 145 + i * 60 - self.pause_scroll, 150, 34)
            for i, (_, _, key, _, _) in enumerate(self._pause_settings_rows())
        }
        return panel, buttons, toggles

    def _pause_settings_rows(self) -> list[tuple[str, bool, str, str, str]]:
        return [
            ("Automatic art hot reload", self.hot_reload_enabled, "hot_reload", "", ""),
            ("Mouse camera look-ahead", bool(self.settings.get("camera", {}).get("lookahead_enabled", True)), "lookahead", "camera", "lookahead_enabled"),
            ("Camera look-ahead debug", bool(self.settings.get("debug", {}).get("show_camera_lookahead", False)), "camera_debug", "debug", "show_camera_lookahead"),
            ("Camera-relative walking", bool(self.settings.get("controls", {}).get("camera_relative_movement", True)), "camera_relative", "controls", "camera_relative_movement"),
            ("Middle-mouse camera rotation", bool(self.settings.get("camera", {}).get("rotation_enabled", True)), "rotation", "camera", "rotation_enabled"),
            ("Center player while rotated", bool(self.settings.get("camera", {}).get("center_player_when_rotated", True)), "center_rotated", "camera", "center_player_when_rotated"),
        ]

    def _pause_friend_rows(self) -> list[tuple[str, bool]]:
        online = {
            str(row.get("name", "Player"))[:24]
            for pid, row in self.map_players.items() if pid != self.local_id
        }
        rows = [(name, True) for name in sorted(online, key=str.casefold)]
        online_keys = {name.casefold() for name in online}
        rows.extend(
            (name, False) for name in sorted(self.friend_names.values(), key=str.casefold)
            if name.casefold() not in online_keys
        )
        return rows

    def _pause_max_scroll(self) -> int:
        panel, _, _ = self._pause_layout()
        visible_h = panel.height - 235
        count = len(self._pause_settings_rows()) if self.pause_page == "settings" else len(self._pause_friend_rows())
        return max(0, count * 60 - visible_h)

    def scroll_pause_page(self, amount: int) -> None:
        if self.pause_page not in {"settings", "friends"}:
            return
        self.pause_scroll = max(0, min(self._pause_max_scroll(), self.pause_scroll + int(amount)))

    def _draw_menu_button(self, rect: pygame.Rect, label: str, active: bool = False) -> None:
        style = self.art_style.get("ui", {})
        panel2 = tuple(style.get("panel_2", (38,41,40)))
        accent = tuple(style.get("accent", INV_SELECTED))
        pygame.draw.rect(self.screen, panel2, rect, border_radius=6)
        pygame.draw.rect(self.screen, accent if active else MUTED_TEXT, rect, width=2, border_radius=6)
        txt = self.small_font.render(label, True, TEXT_COLOR)
        self.screen.blit(txt, txt.get_rect(center=rect.center))

    def draw_pause_menu(self) -> None:
        if not self.pause_menu_open:
            return
        sw, sh = self.screen.get_size()
        shade = pygame.Surface((sw, sh), pygame.SRCALPHA)
        shade.fill((0,0,0,190))
        self.screen.blit(shade, (0,0))
        panel, buttons, toggles = self._pause_layout()
        ui = self.art_style.get("ui", {})
        panel_color = tuple(ui.get("panel", (28,31,31)))
        accent = tuple(ui.get("accent", INV_SELECTED))
        panel_edge = tuple(ui.get("panel_edge", accent))
        pygame.draw.rect(self.screen, panel_color, panel, border_radius=6)
        pygame.draw.rect(self.screen, panel_edge, panel, width=3, border_radius=6)
        pygame.draw.line(self.screen, accent, (panel.x+12,panel.y+8), (panel.right-12,panel.y+8), 2)
        title = self.big_font.render("PAUSED / OPTIONS", True, TEXT_COLOR)
        self.screen.blit(title, (panel.x + 32, panel.y + 24))

        if self.pause_page == "settings":
            self.screen.blit(self.font.render("SETTINGS", True, accent), (panel.x + 32, panel.y + 92))
            content = pygame.Rect(panel.x + 24, panel.y + 132, panel.width - 48, panel.height - 218)
            old_clip = self.screen.get_clip()
            self.screen.set_clip(content)
            y = panel.y + 145 - self.pause_scroll
            for label, state, key, _, _ in self._pause_settings_rows():
                self.screen.blit(self.font.render(label, True, TEXT_COLOR), (panel.x + 48, y + 6))
                self._draw_menu_button(toggles[key], "ON" if state else "OFF", active=state)
                y += 60
            self.screen.set_clip(old_clip)
            self.screen.blit(self.tiny_font.render("Mouse wheel / Up / Down scrolls settings", True, MUTED_TEXT), (panel.x + 190, panel.bottom - 52))
            self._draw_menu_button(buttons["back"], "BACK")
            return

        if self.pause_page == "friends":
            self.screen.blit(self.font.render("FRIENDS / ONLINE PLAYERS", True, accent), (panel.x + 32, panel.y + 92))
            content = pygame.Rect(panel.x + 24, panel.y + 132, panel.width - 48, panel.height - 218)
            old_clip = self.screen.get_clip()
            self.screen.set_clip(content)
            rows = self._pause_friend_rows()
            if not rows:
                self.screen.blit(self.font.render("No other players are online yet.", True, MUTED_TEXT), (panel.x + 48, panel.y + 154))
            for i, (name, online) in enumerate(rows):
                y = panel.y + 145 + i * 60 - self.pause_scroll
                state = self.is_friend(name)
                status = "ONLINE" if online else "OFFLINE"
                self.screen.blit(self.font.render(name, True, REMOTE_COLOR if online else MUTED_TEXT), (panel.x + 48, y + 4))
                self.screen.blit(self.tiny_font.render(status, True, (145, 226, 160) if online else MUTED_TEXT), (panel.x + 48, y + 29))
                rect = pygame.Rect(panel.right - 210, y, 150, 34)
                self._draw_menu_button(rect, "REMOVE" if state else "ADD FRIEND", active=state)
            self.screen.set_clip(old_clip)
            self.screen.blit(self.tiny_font.render("Friends appear on the minimap; /w Name message sends a whisper", True, MUTED_TEXT), (panel.x + 190, panel.bottom - 52))
            self._draw_menu_button(buttons["back"], "BACK")
            return

        self.screen.blit(self.font.render("CONTROLS", True, accent), (panel.x + 32, panel.y + 82))
        controls = [
            "WASD / arrows    Move / drive",
            "SHIFT            Sprint on foot / full throttle in car (up to 88 mph)",
            "Mouse            Bounded camera look-ahead",
            "Space            Jump",
            "C                Crouch (hold)",
            "Middle mouse     Hold + drag to rotate camera",
            "Mouse wheel      Zoom world view in / out (0.55x - 2.0x)",
            "T                Enter/steal/exit car or bicycle",
            "E                Interact / enter interior",
            "I or TAB         Inventory",
            "M                World map",
            "F5               Reload art style + settings",
            "F6               Rebuild current visual chunk",
            "F7               Rebuild nearby 3x3 visual chunks",
            "F8               Clear/rebuild all rendered chunks on demand",
            "F9               Toggle A1 chunk debug overlay",
            "F10 or /bug      Save screenshot + next-version feedback",
            "ESC              Open/close this menu",
        ]
        y = panel.y + 122
        for line in controls:
            self.screen.blit(self.small_font.render(line, True, TEXT_COLOR), (panel.x + 48, y))
            y += 27
        hot = "ON" if self.hot_reload_enabled else "OFF"
        self.screen.blit(self.tiny_font.render(f"Automatic art hot reload: {hot}   •   persistent shared assets/data enabled", True, MUTED_TEXT), (panel.x + 48, panel.bottom - 108))
        self._draw_menu_button(buttons["resume"], "RESUME")
        self._draw_menu_button(buttons["settings"], "SETTINGS")
        self._draw_menu_button(buttons["friends"], "FRIENDS")
        self._draw_menu_button(buttons["quit"], "QUIT GAME")

    def handle_pause_click(self, pos: tuple[int,int]) -> str | None:
        if not self.pause_menu_open:
            return None
        _, buttons, toggles = self._pause_layout()
        if self.pause_page == "settings":
            if buttons["back"].collidepoint(pos):
                self.pause_page = "main"
                return None
            panel, _, _ = self._pause_layout()
            content = pygame.Rect(panel.x + 24, panel.y + 132, panel.width - 48, panel.height - 218)
            for _, state, key, section, setting_key in self._pause_settings_rows():
                if content.collidepoint(pos) and toggles[key].collidepoint(pos):
                    if key == "hot_reload":
                        self.hot_reload_enabled = not self.hot_reload_enabled
                        set_art_style_value("hot_reload", "enabled", self.hot_reload_enabled)
                        self.style_watcher.reset()
                    else:
                        set_setting_value(section, setting_key, not state)
                        self.settings = load_settings()
                        self.camera_controller.tuning = dict(self.settings.get("camera", {}))
                        self.camera_rotation_enabled = bool(self.settings.get("camera", {}).get("rotation_enabled", True))
                        self.camera_center_player_when_rotated = bool(self.settings.get("camera", {}).get("center_player_when_rotated", True))
                    return None
        elif self.pause_page == "friends":
            if buttons["back"].collidepoint(pos):
                self.pause_page = "main"
                self.pause_scroll = 0
                return None
            panel, _, _ = self._pause_layout()
            content = pygame.Rect(panel.x + 24, panel.y + 132, panel.width - 48, panel.height - 218)
            for i, (name, _) in enumerate(self._pause_friend_rows()):
                rect = pygame.Rect(panel.right - 210, panel.y + 145 + i * 60 - self.pause_scroll, 150, 34)
                if content.collidepoint(pos) and rect.collidepoint(pos):
                    self.toggle_friend(name)
                    return None
            return None
        if buttons["resume"].collidepoint(pos):
            self.pause_menu_open = False
        elif buttons["settings"].collidepoint(pos):
            self.pause_page = "settings"
            self.pause_scroll = 0
        elif buttons["friends"].collidepoint(pos):
            self.pause_page = "friends"
            self.pause_scroll = 0
        elif buttons["quit"].collidepoint(pos):
            return "quit"
        return None

    def _nearest_named_map_feature(self, local) -> tuple[str, str]:
        candidates: list[tuple[float, str, str]] = []
        for feature in self.map_config.get("landmarks", []) or []:
            pos = feature.get("pos", [0, 0])
            try:
                dist = math.hypot(local.render_x - float(pos[0]), local.render_y - float(pos[1]))
            except (TypeError, ValueError, IndexError):
                continue
            candidates.append((dist, str(feature.get("name", "LANDMARK")), str(feature.get("kind", "LANDMARK"))))
        for feature in self.map_config.get("districts", []) or []:
            pos = feature.get("pos", [0, 0])
            try:
                dist = math.hypot(local.render_x - float(pos[0]), local.render_y - float(pos[1]))
            except (TypeError, ValueError, IndexError):
                continue
            candidates.append((dist, str(feature.get("name", "DISTRICT")), "DISTRICT"))
        if not candidates:
            return "FORT LEE / GWB", "DISTRICT"
        candidates.sort(key=lambda item: item[0])
        return candidates[0][1], candidates[0][2]

    def draw_local_minimap(self) -> None:
        local = self.players.get(self.local_id or "")
        if local is None:
            return
        ui = self.art_style.get("ui", {})
        env = self.art_style.get("environment", {})
        diameter = 194
        radius = diameter // 2
        world_radius = 1050.0 if getattr(local, "in_vehicle", False) else 760.0
        scale = radius / world_radius
        mini = pygame.Surface((diameter, diameter), pygame.SRCALPHA)
        panel = tuple(ui.get("minimap_background", (54, 58, 56)))
        road_color = tuple(ui.get("minimap_road", (110, 112, 107)))
        water_color = tuple(ui.get("minimap_water", env.get("water", (47,72,84))))
        border = tuple(ui.get("minimap_border", (27,28,27)))
        mini.fill((*panel, 235))

        def mp(point):
            return (
                int(radius + (float(point[0]) - local.render_x) * scale),
                int(radius + (float(point[1]) - local.render_y) * scale),
            )

        for poly in self.map_config.get("water_polygons", []) or []:
            pts = [mp(p) for p in poly if isinstance(p, (list, tuple)) and len(p) >= 2]
            if len(pts) >= 3:
                pygame.draw.polygon(mini, water_color, pts)
        for road in self.map_config.get("roads", []) or []:
            pts_raw = road.get("points", []) or []
            if len(pts_raw) < 2:
                continue
            pts = [mp(p) for p in pts_raw]
            try:
                width = max(2, min(12, int(float(road.get("width", 36)) * scale)))
            except (TypeError, ValueError):
                width = 3
            pygame.draw.lines(mini, road_color, False, pts, width)
        for prop in self.map_config.get("street_props", []) or []:
            if str(prop.get("kind", "")) != "edge_tunnel":
                continue
            p = mp(prop.get("pos", [0, 0]))
            angle = math.radians(float(prop.get("rotation", 0.0)))
            nx, ny = -math.sin(angle), math.cos(angle)
            half = max(2, min(5, int(round(float(prop.get("scale", 1.0)) * 2.0))))
            pygame.draw.line(mini, (5, 6, 7), (int(p[0]-nx*half),int(p[1]-ny*half)), (int(p[0]+nx*half),int(p[1]+ny*half)), 3)

        # A1-style streaming grid on the minimap. It remains north-up even when
        # the gameplay camera rotates, matching the full world map/compiler IDs.
        chunk_size = max(1, int(self.map_config.get("chunk_size", 1024)))
        cols = max(1, int(self.map_config.get("chunk_cols", math.ceil(float(self.map_config.get("world_w", 1)) / chunk_size))))
        rows = max(1, int(self.map_config.get("chunk_rows", math.ceil(float(self.map_config.get("world_h", 1)) / chunk_size))))
        grid_col = (135, 139, 133)
        gx0 = max(0, int((local.render_x - world_radius) // chunk_size))
        gy0 = max(0, int((local.render_y - world_radius) // chunk_size))
        gx1 = min(cols - 1, int((local.render_x + world_radius) // chunk_size))
        gy1 = min(rows - 1, int((local.render_y + world_radius) // chunk_size))
        for gx in range(gx0, gx1 + 2):
            wx = gx * chunk_size
            px = int(radius + (wx - local.render_x) * scale)
            if 0 <= px < diameter:
                pygame.draw.line(mini, grid_col, (px, 0), (px, diameter - 1), 1)
        for gy in range(gy0, gy1 + 2):
            wy = gy * chunk_size
            py = int(radius + (wy - local.render_y) * scale)
            if 0 <= py < diameter:
                pygame.draw.line(mini, grid_col, (0, py), (diameter - 1, py), 1)
        for gy in range(gy0, gy1 + 1):
            for gx in range(gx0, gx1 + 1):
                center_world = ((gx + 0.5) * chunk_size, (gy + 0.5) * chunk_size)
                lp = mp(center_world)
                if 8 <= lp[0] < diameter - 8 and 8 <= lp[1] < diameter - 8:
                    lab = self.tiny_font.render(chunk_label(gx, gy), True, (224, 225, 218))
                    mini.blit(lab, lab.get_rect(center=lp))

        # Darken outside a perfect circular mask.
        circle_mask = pygame.Surface((diameter, diameter), pygame.SRCALPHA)
        pygame.draw.circle(circle_mask, (255,255,255,255), (radius,radius), radius-3)
        mini.blit(circle_mask, (0,0), special_flags=pygame.BLEND_RGBA_MULT)
        pygame.draw.circle(mini, border, (radius,radius), radius-2, width=7)
        # The compact minimap is deliberately private/friend-focused. The full
        # M map retains the complete online roster for general orientation.
        for pid, marker in self.map_players.items():
            if pid == self.local_id or not self.is_friend(str(marker.get("name", ""))):
                continue
            try:
                dx = float(marker.get("x", 0.0)) - local.render_x
                dy = float(marker.get("y", 0.0)) - local.render_y
            except (TypeError, ValueError):
                continue
            if dx * dx + dy * dy > (world_radius * 0.94) ** 2:
                continue
            friend_pos = (int(radius + dx * scale), int(radius + dy * scale))
            pygame.draw.circle(mini, (18, 24, 28), friend_pos, 6)
            pygame.draw.circle(mini, REMOTE_COLOR, friend_pos, 4)
        pygame.draw.circle(mini, tuple(ui.get("accent", LOCAL_COLOR)), (radius,radius), 5)
        heading = float(getattr(local, "aim", 0.0))
        tip = (int(radius + math.cos(heading)*16), int(radius + math.sin(heading)*16))
        left = (int(radius + math.cos(heading+2.55)*9), int(radius + math.sin(heading+2.55)*9))
        right = (int(radius + math.cos(heading-2.55)*9), int(radius + math.sin(heading-2.55)*9))
        pygame.draw.polygon(mini, (244,244,237), [tip,left,right])
        pygame.draw.polygon(mini, border, [tip,left,right], width=1)
        self.screen.blit(mini, (18, self.screen.get_height() - diameter - 58))
        n = self.small_font.render("N", True, TEXT_COLOR)
        self.screen.blit(n, (18 + radius - n.get_width()//2, self.screen.get_height() - diameter - 53))

        name, _kind = self._nearest_named_map_feature(local)
        label = str(name).upper()
        ccx, ccy = world_to_chunk(local.render_x, local.render_y, self.map_config)
        label = f"{label[:20]}  •  {chunk_label(ccx, ccy)}"
        label_s = self.small_font.render(label[:30], True, TEXT_COLOR)
        box = pygame.Rect(18, self.screen.get_height()-52, max(194, label_s.get_width()+28), 38)
        pygame.draw.rect(self.screen, tuple(ui.get("panel", (28,31,31))), box, border_radius=3)
        pygame.draw.rect(self.screen, tuple(ui.get("panel_edge", (92,92,84))), box, width=1, border_radius=3)
        self.screen.blit(label_s, label_s.get_rect(center=box.center))

    def draw_chunk_debug_overlay(self) -> None:
        if not self.chunk_debug_overlay:
            return
        local = self.players.get(self.local_id or "")
        if local is None:
            return
        chunk_size = max(1, int(self.map_config.get("chunk_size", 1024)))
        cx, cy = world_to_chunk(local.render_x, local.render_y, self.map_config)
        lx = int(local.render_x - cx * chunk_size)
        ly = int(local.render_y - cy * chunk_size)
        lines = [
            f"CHUNK {chunk_label(cx, cy)}  ({cx},{cy})",
            f"WORLD {int(local.render_x)}, {int(local.render_y)}",
            f"LOCAL {lx}, {ly} / {chunk_size}",
        ]
        widest = max(self.small_font.size(line)[0] for line in lines) + 22
        box = pygame.Rect(self.screen.get_width() - widest - 18, 18, widest, 70)
        pygame.draw.rect(self.screen, (22, 25, 25), box, border_radius=4)
        pygame.draw.rect(self.screen, (122, 126, 119), box, width=1, border_radius=4)
        for i, line in enumerate(lines):
            self.screen.blit(self.small_font.render(line, True, TEXT_COLOR), (box.x + 11, box.y + 8 + i * 19))

    def draw_location_plaque(self) -> None:
        local = self.players.get(self.local_id or "")
        if local is None:
            return
        name, kind = self._nearest_named_map_feature(local)
        ui = self.art_style.get("ui", {})
        line1 = str(name).upper()[:34]
        line2 = "UPPER LEVEL" if "WASHINGTON BRIDGE" in line1 or "GWB" in line1 else str(kind).replace("_", " ").upper()
        a = self.small_font.render(line1, True, TEXT_COLOR)
        b = self.small_font.render(line2, True, TEXT_COLOR)
        width = max(236, a.get_width()+30, b.get_width()+30)
        box = pygame.Rect(self.screen.get_width()-width-18, self.screen.get_height()-78, width, 64)
        pygame.draw.rect(self.screen, tuple(ui.get("panel", (28,31,31))), box, border_radius=3)
        pygame.draw.rect(self.screen, tuple(ui.get("panel_edge", (92,92,84))), box, width=1, border_radius=3)
        self.screen.blit(a, (box.x+14, box.y+10))
        self.screen.blit(b, (box.x+14, box.y+34))

    def draw_hud(self) -> None:
        w, h = self.screen.get_size()
        local = self.players.get(self.local_id or "")
        ui = self.art_style.get("ui", {})
        panel_rgb = tuple(ui.get("panel", (28,31,31)))
        panel_edge = tuple(ui.get("panel_edge", (92,92,84)))
        panel = pygame.Surface((350, 112), pygame.SRCALPHA)
        panel.fill((*panel_rgb, 220))
        self.screen.blit(panel, (18, 18))
        pygame.draw.rect(self.screen, panel_edge, (18,18,350,112), width=2, border_radius=3)
        pygame.draw.line(self.screen, tuple(ui.get("accent", LOCAL_COLOR)), (26,24), (360,24), 2)
        status = "ONLINE" if self.connected else "OFFLINE"
        self.screen.blit(self.small_font.render(status, True, (160, 235, 170) if self.connected else (240, 130, 130)), (30, 28))
        if local:
            self.screen.blit(self.big_font.render(f"${local.cash}", True, TEXT_COLOR), (30, 48))
            count = inventory_count(self.inventory, "package")
            self.screen.blit(self.font.render(f"Inventory: {count} package{'s' if count != 1 else ''}   [I]", True, TEXT_COLOR), (30, 83))
            supplier_pos = self.map_config["supplier_pos"]
            near_supplier = math.hypot(local.render_x - supplier_pos[0], local.render_y - supplier_pos[1]) <= INTERACT_DISTANCE
            sales_targets: list[tuple[float, str]] = []
            for player in self.players.values():
                if player.id == self.local_id or player.in_vehicle or player.interior_id != local.interior_id:
                    continue
                d = math.hypot(local.render_x - player.render_x, local.render_y - player.render_y)
                if d <= INTERACT_DISTANCE:
                    sales_targets.append((d, player.name))
            if not local.interior_id:
                for npc in self.npcs.values():
                    d = math.hypot(local.render_x - npc.render_x, local.render_y - npc.render_y)
                    if d <= INTERACT_DISTANCE:
                        sales_targets.append((d, "PEDESTRIAN"))
            if (near_supplier or sales_targets) and not self.inventory_open:
                target = "BUY" if near_supplier else f"SELL TO {min(sales_targets, key=lambda row: row[0])[1].upper()}"
                prompt = self.big_font.render(f"[ E ] {target}", True, LOCAL_COLOR)
                pr = prompt.get_rect(center=(w // 2, h - 72))
                pygame.draw.rect(self.screen, (10, 10, 10), pr.inflate(32, 22), border_radius=7)
                self.screen.blit(prompt, pr)
        map_name = str(self.map_config.get("name", "Unknown map"))
        local_chunk = self.server_chunk
        online_count = len(self.map_players) if self.map_players else len(self.players)
        players_text = self.small_font.render(f"{map_name}   chunk {chunk_label(local_chunk[0], local_chunk[1])} / {self.server_region_id}   online:{online_count} nearby:{len(self.players)} cars:{len(self.vehicles)} bikes:{len(self.bicycles)} peds:{len(self.npcs)}   [2× DIR] 3× run  [SHIFT] legacy sprint/vehicle boost  [T] mobility  [M] map  [F10] report", True, TEXT_COLOR)
        self.screen.blit(players_text, (w - players_text.get_width() - 20, 20))
        self.draw_vehicle_status()
        self.draw_local_minimap()
        self.draw_chunk_debug_overlay()
        self.draw_location_plaque()
        if bool(self.settings.get("debug", {}).get("show_camera_lookahead", False)):
            cx, cy = w // 2, h // 2
            lx = int(cx + self.camera_controller.look_x)
            ly = int(cy + self.camera_controller.look_y)
            pygame.draw.line(self.screen, (120, 170, 210), (cx, cy), (lx, ly), 1)
            pygame.draw.circle(self.screen, (120, 170, 210), (lx, ly), 4, width=1)
        if time.monotonic() < self.notice_until:
            notice = self.font.render(self.notice, True, TEXT_COLOR)
            rect = notice.get_rect(center=(w // 2, 34))
            pygame.draw.rect(self.screen, (10, 10, 10), rect.inflate(24, 14), border_radius=6)
            self.screen.blit(notice, rect)

    async def run(self) -> None:
        running = True
        try:
            while running:
                dt = min(0.05, self.clock.tick(FPS) / 1000.0)
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        running = False
                    elif event.type == pygame.KEYDOWN:
                        if self.handle_issue_report_key(event):
                            continue
                        if self.handle_chat_key(event):
                            continue
                        if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER) and not self.pause_menu_open and not self.inventory_open and not self.map_open:
                            self.chat_active = True
                            self.chat_text = ""
                            self.cancel_direction_sprint()
                            continue
                        if self.pause_menu_open and self.pause_page in {"settings", "friends"}:
                            if event.key in (pygame.K_UP, pygame.K_PAGEUP, pygame.K_HOME):
                                self.scroll_pause_page(-240 if event.key == pygame.K_PAGEUP else (-60 if event.key == pygame.K_UP else -100000))
                                continue
                            if event.key in (pygame.K_DOWN, pygame.K_PAGEDOWN, pygame.K_END):
                                self.scroll_pause_page(240 if event.key == pygame.K_PAGEDOWN else (60 if event.key == pygame.K_DOWN else 100000))
                                continue
                        if event.key in (pygame.K_w, pygame.K_a, pygame.K_s, pygame.K_d, pygame.K_UP, pygame.K_LEFT, pygame.K_DOWN, pygame.K_RIGHT) and not getattr(event, "repeat", False):
                            self.register_direction_tap(event.key)
                        # Manual reload keys always work and are documented on ESC.
                        if event.key == pygame.K_F5:
                            self.reload_visual_style(manual=True)
                            continue
                        if event.key == pygame.K_F6:
                            self.manual_chunk_reload("current")
                            continue
                        if event.key == pygame.K_F7:
                            self.manual_chunk_reload("near")
                            continue
                        if event.key == pygame.K_F8:
                            self.manual_chunk_reload("all")
                            continue
                        if event.key == pygame.K_F9:
                            self.chunk_debug_overlay = not self.chunk_debug_overlay
                            self.notice = f"A1 chunk debug overlay {'ON' if self.chunk_debug_overlay else 'OFF'}"
                            self.notice_until = time.monotonic() + 1.5
                            continue
                        if self.interior.active:
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
                        if event.key == pygame.K_ESCAPE:
                            if self.pause_menu_open:
                                self.pause_menu_open = False
                                self.pause_page = "main"
                            elif self.map_open:
                                self.map_open = False
                            elif self.inventory_open:
                                self.inventory_open = False
                            else:
                                self.pause_menu_open = True
                                self.pause_page = "main"
                            continue
                        if self.pause_menu_open:
                            continue
                        if event.key == pygame.K_SPACE and not self.inventory_open and not self.map_open:
                            local = self.players.get(self.local_id or "")
                            if local is not None and not bool(getattr(local, "in_vehicle", False)):
                                self.jump_request_pending = True
                            continue
                        if event.key == pygame.K_m:
                            self.map_open = not self.map_open
                            if self.map_open:
                                self.inventory_open = False
                        elif event.key in (pygame.K_i, pygame.K_TAB) and not self.map_open:
                            self.inventory_open = not self.inventory_open
                            if self.inventory_open:
                                self.network.send({"type": "inventory_request"})
                        elif event.key == pygame.K_e and not self.inventory_open and not self.map_open:
                            if not self.try_enter_interior():
                                self.network.send({"type": "interact"})
                        elif event.key == pygame.K_t and not self.inventory_open and not self.map_open:
                            self.network.send({"type": "car_action"})
                        elif self.inventory_open and event.key in (pygame.K_LEFT, pygame.K_RIGHT, pygame.K_UP, pygame.K_DOWN):
                            row, col = divmod(self.selected_slot, INVENTORY_COLS)
                            if event.key == pygame.K_LEFT:
                                col = max(0, col - 1)
                            elif event.key == pygame.K_RIGHT:
                                col = min(INVENTORY_COLS - 1, col + 1)
                            elif event.key == pygame.K_UP:
                                row = max(0, row - 1)
                            elif event.key == pygame.K_DOWN:
                                row = min(INVENTORY_ROWS - 1, row + 1)
                            self.selected_slot = row * INVENTORY_COLS + col
                    elif event.type == pygame.KEYUP:
                        if event.key == self.sprint_trigger_key:
                            self.cancel_direction_sprint()
                    elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 2:
                        if self.issue_report_open:
                            continue
                        if not self.pause_menu_open and not self.inventory_open and not self.map_open and not self.interior.active:
                            self.camera_rotation_dragging = True
                    elif event.type == pygame.MOUSEBUTTONUP and event.button == 2:
                        if self.camera_rotation_dragging:
                            self.camera_rotation_dragging = False
                            self.finish_camera_rotation()
                    elif event.type == pygame.MOUSEMOTION and self.camera_rotation_dragging:
                        self.adjust_camera_rotation(event.rel[0])
                    elif event.type == pygame.MOUSEWHEEL:
                        if self.issue_report_open:
                            continue
                        if self.pause_menu_open and self.pause_page in {"settings", "friends"}:
                            self.scroll_pause_page(-event.y * 48)
                        elif not self.inventory_open and not self.map_open and not self.pause_menu_open and not self.interior.active:
                            self.adjust_camera_zoom(event.y)
                    elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                        if self.issue_report_open:
                            continue
                        if self.pause_menu_open:
                            if self.handle_pause_click(event.pos) == "quit":
                                running = False
                            continue
                        if self.inventory_open:
                            slot = self.inventory_slot_at(event.pos)
                            if slot is not None:
                                self.selected_slot = slot
                                if self.inventory[slot] is not None:
                                    self.drag_source = slot
                    elif event.type == pygame.MOUSEBUTTONUP and event.button == 1 and self.inventory_open:
                        if self.drag_source is not None:
                            target = self.inventory_slot_at(event.pos)
                            if target is not None and target != self.drag_source:
                                self.network.send({"type": "inventory_move", "source": self.drag_source, "target": target})
                                self.selected_slot = target
                            self.drag_source = None

                self.poll_hot_reload()
                self.process_network()
                for pid, player in self.players.items():
                    player.smooth(dt, local=(pid == self.local_id))
                for car in self.vehicles.values():
                    car.smooth(dt)
                for bike in self.bicycles.values():
                    bike.smooth(dt)
                for npc in self.npcs.values():
                    npc.smooth(dt)
                self.update_camera(dt)
                self.send_input()
                if self.interior.active:
                    occupants = []
                    now = time.monotonic()
                    for pid, player in self.players.items():
                        if pid != self.local_id and player.interior_id != self.interior.room_id:
                            continue
                        is_local = pid == self.local_id
                        occupants.append({
                            "name": player.name,
                            "appearance": player.appearance,
                            "x": self.interior.player_x if is_local else player.interior_x,
                            "y": self.interior.player_y if is_local else player.interior_y,
                            "aim": self.interior.player_aim if is_local else player.interior_aim,
                            "moving": now < (self.interior.player_moving_until if is_local else player.moving_until),
                            "anim_time": now - (self.interior.player_anim_epoch if is_local else player.anim_epoch),
                            "local": is_local,
                            "bubble": self.chat_bubbles.get(pid) if time.monotonic() < float(self.chat_bubbles.get(pid, {}).get("until", 0.0)) else None,
                        })
                    self.interior.draw(
                        self.screen, self.font, self.small_font,
                        appearance=(self.players.get(self.local_id or "").appearance if self.players.get(self.local_id or "") is not None else CHARACTER_DEFAULT),
                        occupants=occupants,
                    )
                else:
                    display_surface = self.screen
                    view_size = self.logical_view_size()
                    rotation_active = self.camera_rotation_enabled and abs(self.camera_rotation_degrees % 360.0) > 0.01
                    if rotation_active:
                        # Render only the inverse-rotated bounding rectangle needed
                        # to cover the viewport. The old diagonal square could be
                        # more than twice as many pixels near 90-degree rotation.
                        theta = math.radians(self.camera_rotation_degrees)
                        c, sn = abs(math.cos(theta)), abs(math.sin(theta))
                        rw = int(math.ceil(view_size[0] * c + view_size[1] * sn)) + 8
                        rh = int(math.ceil(view_size[0] * sn + view_size[1] * c)) + 8
                        render_size = (max(view_size[0]//2, rw), max(view_size[1]//2, rh))
                        local = self.players.get(self.local_id or "")
                        if local is not None:
                            cx, cy = float(local.render_x), float(local.render_y)
                        else:
                            cx, cy = self.camera_controller.center(view_size)
                        self._render_camera_override = (cx - render_size[0] * 0.5, cy - render_size[1] * 0.5)
                    else:
                        render_size = view_size
                        self._render_camera_override = None
                    if self._zoom_world_surface is None or self._zoom_world_surface_size != render_size:
                        self._zoom_world_surface = pygame.Surface(render_size).convert()
                        self._zoom_world_surface_size = render_size
                    world_surface = self._zoom_world_surface
                    self.screen = world_surface
                    self.draw_world()
                    for stain in self.blood_stains.values():
                        self.draw_blood_stain(stain)
                    # Grade-separated dynamic draw order.  Vehicles/NPC traffic is
                    # still a Level-0 system; pedestrian players carry authoritative
                    # map levels.  Each elevated deck is redrawn after lower-level
                    # entities and before players standing on that deck.
                    drawables = []
                    drawables.extend((self.camera_depth(car.render_x, car.render_y), "car", car) for car in self.vehicles.values())
                    drawables.extend((self.camera_depth(bike.render_x, bike.render_y), "bike", bike) for bike in self.bicycles.values())
                    drawables.extend((self.camera_depth(npc.render_x, npc.render_y), "npc", npc) for npc in self.npcs.values())
                    drawables.extend(
                        (self.camera_depth(player.render_x, player.render_y), "player", player)
                        for player in self.players.values() if int(getattr(player, "level", 0)) <= 0
                    )
                    for _, kind, obj in sorted(drawables, key=lambda row: row[0]):
                        if kind == "car": self.draw_vehicle(obj)
                        elif kind == "bike": self.draw_bicycle_entity(obj)
                        elif kind == "npc": self.draw_npc(obj)
                        else: self.draw_player(obj, local=(obj.id == self.local_id))

                    positive_levels = sorted({
                        int(float(road.get("level", 0) or 0))
                        for road in self.map_config.get("roads", []) or []
                        if int(float(road.get("level", 0) or 0)) > 0
                    })
                    for map_level in positive_levels:
                        self.environment.draw_elevated_overlay(self.screen, self.camera(), map_level)
                        level_players = [
                            (self.camera_depth(player.render_x, player.render_y), player)
                            for player in self.players.values()
                            if int(getattr(player, "level", 0)) == map_level
                        ]
                        for _, player in sorted(level_players, key=lambda row: row[0]):
                            self.draw_player(player, local=(player.id == self.local_id))
                    self.screen = display_surface
                    self._render_camera_override = None
                    if rotation_active:
                        filtered = bool(self.settings.get("render", {}).get("filtered_rotation", True))
                        fast_drag = bool(self.settings.get("render", {}).get("fast_rotation_while_dragging", True))
                        if filtered and not (self.camera_rotation_dragging and fast_drag):
                            rotated = pygame.transform.rotozoom(world_surface, self.camera_rotation_degrees, 1.0)
                        else:
                            rotated = pygame.transform.rotate(world_surface, self.camera_rotation_degrees)
                        crop = pygame.Rect(0, 0, view_size[0], view_size[1])
                        crop.center = rotated.get_rect().center
                        final_world = rotated.subsurface(crop)
                    else:
                        final_world = world_surface
                    # 0.85x is a fractional downscale. Nearest-neighbor downsampling
                    # produces uneven pixel dropping/shimmer, so use one filtered
                    # downscale pass below 1x. At >=1x retain nearest scaling to keep
                    # the approved pixel-art edges crisp.
                    filter_name = str(self.settings.get("render", {}).get("fractional_zoom_filter", "smooth")).strip().lower()
                    if self.camera_zoom < 0.999 and filter_name == "smooth":
                        pygame.transform.smoothscale(final_world, display_surface.get_size(), display_surface)
                    else:
                        pygame.transform.scale(final_world, display_surface.get_size(), display_surface)
                    # Nameplates are screen-space UI and therefore stay horizontal
                    # at every camera angle.
                    self.draw_player_nameplates()
                    self.draw_hud()
                    zoom_text = self.tiny_font.render(f"ZOOM {self.camera_zoom:.2f}x", True, MUTED_TEXT)
                    self.screen.blit(zoom_text, (self.screen.get_width()-zoom_text.get_width()-18, 48))
                    rot_text = self.tiny_font.render(f"ROT {self.camera_rotation_degrees%360:05.1f}°", True, MUTED_TEXT)
                    self.screen.blit(rot_text, (self.screen.get_width()-rot_text.get_width()-18, 64))
                    self.draw_world_map()
                    self.draw_inventory()
                self.draw_chat_input()
                self.draw_pause_menu()
                self.draw_issue_reporter()
                pygame.display.flip()
                # Yield once per frame so pygbag can return control to the
                # browser event loop. This is effectively free on desktop.
                await asyncio.sleep(0)
        finally:
            self.network.stop()
            pygame.quit()


async def main() -> None:
    parser = argparse.ArgumentParser(description="Pygame multiplayer vertical slice client")
    parser.add_argument("--server", default=None, help="WebSocket server URI; supplying this bypasses launcher")
    parser.add_argument("--name", default=None, help="Display name")
    parser.add_argument("--phone", default=None, help="Phone-number account identifier")
    parser.add_argument("--no-launcher", action="store_true", help="Connect directly to localhost")
    args = parser.parse_args()

    if sys.platform == "emscripten":
        # Browser builds bypass desktop LAN discovery/launcher threads. The
        # enabled public-server CSV entry is the automatic default; ?server=
        # remains an explicit override and page-host localhost is the fallback.
        import platform
        from urllib.parse import parse_qs
        location = platform.window.location
        page_scheme = "wss" if str(location.protocol).lower().startswith("https") else "ws"
        page_host = str(location.hostname) or "127.0.0.1"
        params = parse_qs(str(location.search).lstrip("?"))
        raw_server = (params.get("server") or [""])[0].strip()
        uri = choose_browser_server_uri(raw_server, page_scheme, page_host)
        name = args.name or f"WebPlayer{random.randint(100, 999)}"
        phone = args.phone or random_default_phone()
        appearance = normalize_character(CHARACTER_DEFAULT)
        appearance_changed = False
    elif args.server is not None or args.no_launcher:
        uri = args.server or "ws://127.0.0.1:8765"
        name = args.name or f"Player{random.randint(100, 999)}"
        phone = args.phone or random_default_phone()
        appearance = normalize_character(CHARACTER_DEFAULT)
        appearance_changed = False
    else:
        result = Launcher(args.name, args.phone).run()
        if result is None:
            pygame.quit()
            return
        uri, phone, name, appearance, appearance_changed = result
    await Game(uri, phone, name, appearance, appearance_changed).run()


if __name__ == "__main__":
    asyncio.run(main())
