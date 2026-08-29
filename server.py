from __future__ import annotations

import argparse
import base64
import asyncio
import binascii
import getpass
import hashlib
import hmac
from io import BytesIO
import json
import math
import os
import random
import re
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from websockets.asyncio.server import ServerConnection, serve
from websockets.exceptions import ConnectionClosed

from portable_map_runtime import build_transfer_bundle, load_portable_map

from common import (
    BUY_PRICE,
    DEFAULT_MAP_ID,
    INTERACT_DISTANCE,
    INVENTORY_MAX_WEIGHT_KG,
    ITEM_DEFS,
    MAPS,
    PLAYER_RADIUS,
    PLAYER_SPEED,
    SELL_PRICE,
    SERVER_TICK_RATE,
    SNAPSHOT_RATE,
    TRAFFIC_DEFAULT_COUNT,
    TRAFFIC_FOLLOW_DISTANCE,
    TRAFFIC_PEDESTRIAN_YIELD_DISTANCE,
    TRAFFIC_CAR_COLORS,
    TRAFFIC_CAR_WIDTH,
    TRAFFIC_SPATIAL_CELL,
    TRAFFIC_MIN_SEPARATION,
    TRAFFIC_BRAKE_DECEL,
    TRAFFIC_LOOKAHEAD_MIN,
    NETWORK_INTEREST_RADIUS_CHUNKS,
    world_to_chunk,
    world_to_region,
    region_label,
    PlayerState,
    distance,
    empty_inventory,
    inventory_add,
    inventory_count,
    inventory_remove,
    inventory_weight,
    get_map,
    collision_buildings_near,
    move_with_collisions,
    blocked,
    point_in_water,
    point_near_road,
    resolve_level_transition,
    normalize_character,
    normalize_input,
    traffic_light_states,
    traffic_phase_green,
    reload_maps,
)
from database import DatabaseConfig, InventoryDatabase, mysql_error_text
from vehicle_catalog import vehicle_meta, vehicle_count, load_vehicle_catalog
from mapfiles import validate_map
from mapfiles.grid import chunk_label
from gameplay.settings import load_settings
from gameplay.spatial import build_spatial_grid, nearby_from_grid, nearby_at
from character_catalog import custom_options as character_custom_options, preset_options as character_preset_options, profile_parts as character_profile_parts
from interior_layout import START_TILE as INTERIOR_START_TILE, interior_step
from housing_spawn import blank_house_interiors, house_login_state, overflow_exterior_spawn
from versioning import GAME_VERSION
from grid_runtime import ground_grid_enabled, load_ground_grid, grid_network_metadata
from game_modes import DEFAULT_GAME_MODE_ID, GAME_MODES, get_game_mode

HOST = "0.0.0.0"
PORT = 8765
SERVER_NAME = "Open Night v3.0"
# v2.5 runtime validation replaces this fallback with the exact number of
# enterable GridWorld buildings. Keep the cold-start/default identity aligned
# with the current 30-building map so discovery is never advertised as 128.
MAX_PLAYERS = 30
DISCOVERY_MAGIC = "PYMMO_DISCOVER_V1"
SERVER_VERSION = GAME_VERSION
BUG_REPORT_MAX_SCREENSHOT_BYTES = 1_500_000
BUG_REPORT_COOLDOWN_SECONDS = 45.0
BUG_REPORT_SOURCE_COOLDOWN_SECONDS = 15.0
BUG_REPORT_SESSION_LIMIT = 10
APARTMENT_BUZZER_VISIBILITY_DISTANCE = 135.0
BUG_ADMIN_TOKEN = os.getenv("PYMMO_BUG_ADMIN_TOKEN", "").strip()
BUG_REPORT_SALT = os.getenv("PYMMO_BUG_REPORT_SALT", BUG_ADMIN_TOKEN or "open-night-local").strip()

ACTIVE_MAP_ID = DEFAULT_MAP_ID
ACTIVE_MAP = get_map(ACTIVE_MAP_ID)
GRID_RUNTIME_ACTIVE = ground_grid_enabled(ACTIVE_MAP)
GRID_WORLD = load_ground_grid() if GRID_RUNTIME_ACTIVE else None
ACTIVE_MAP_TRANSFER = None
ACTIVE_GAME_MODE = get_game_mode()
DB: InventoryDatabase | None = None
USE_MYSQL = True
ACTIVE_PORT = PORT
TRAFFIC_COUNT = TRAFFIC_DEFAULT_COUNT
SETTINGS = load_settings()
TRAFFIC_AI = SETTINGS.get("traffic", {})
NPC_AI = SETTINGS.get("npc", {})
BICYCLE_AI = SETTINGS.get("bicycle", {})
MOVEMENT_SETTINGS = SETTINGS.get("movement", {})
VEHICLE_SETTINGS = SETTINGS.get("vehicle", {})
ENGINE_SETTINGS = SETTINGS.get("engine", {})
MAP_ROSTER_RATE = max(0.25, float(ENGINE_SETTINGS.get("world_map_player_roster_hz", 2.0)))
AMBIENT_SIM_RATE = min(float(SERVER_TICK_RATE), 30.0)
LAYER_TRANSITION_JUMP_SECONDS = max(0.0, float(MOVEMENT_SETTINGS.get("layer_transition_jump_seconds", 0.0)))
JUMP_DURATION_SECONDS = max(0.1, float(MOVEMENT_SETTINGS.get("jump_duration_seconds", 0.75)))
DOUBLE_JUMP_WINDOW_SECONDS = max(0.05, float(MOVEMENT_SETTINGS.get("double_jump_window_seconds", 0.55)))
DOUBLE_JUMP_DURATION_SECONDS = max(0.1, float(MOVEMENT_SETTINGS.get("double_jump_duration_seconds", 0.95)))
JUMP_FORWARD_SPEED = max(0.0, float(MOVEMENT_SETTINGS.get("jump_forward_speed_px_per_second", 570.0)))
DOUBLE_JUMP_FORWARD_SPEED = max(0.0, float(MOVEMENT_SETTINGS.get("double_jump_forward_speed_px_per_second", 940.0)))
MOVEMENT_STAND_DELAY_SECONDS = max(0.0, float(MOVEMENT_SETTINGS.get("movement_stand_delay_seconds", 1.0)))
WATER_WALK_SPEED_MULTIPLIER = max(0.05, min(1.0, float(MOVEMENT_SETTINGS.get("water_walk_speed_multiplier", 0.28))))
PASSENGER_CAPACITY = max(1, int(VEHICLE_SETTINGS.get("passenger_capacity", 3)))
PASSENGER_BOARD_MAX_SPEED = max(0.0, float(VEHICLE_SETTINGS.get("passenger_board_max_speed_px_s", 35.0)))
PASSENGER_EXIT_MAX_SPEED = max(0.0, float(VEHICLE_SETTINGS.get("passenger_exit_max_speed_px_s", 70.0)))
HYDRANT_BREAK_MPH = 30.0
HYDRANT_RESPAWN_SECONDS = 300.0
HYDRANT_WATER_SECONDS = 5.0
HYDRANT_HIT_RADIUS = 34.0


def _indexed_character_appearance(index: int, *, preset_only: bool = False) -> dict:
    """Return a varied but completely deterministic character appearance."""
    index = max(0, int(index))
    presets = character_preset_options()
    if preset_only and presets:
        pid = presets[index % len(presets)]
        parts = character_profile_parts(pid, "topdown")
        return normalize_character({"profile": pid, **parts})
    options = character_custom_options()
    appearance = {"profile": "custom"}
    strides = {"hat": 5, "head": 3, "body": 7}
    offsets = {"hat": 1, "head": 2, "body": 4}
    for slot in ("hat", "head", "body"):
        choices = options.get(slot, [])
        if choices:
            appearance[slot] = choices[(index * strides[slot] + offsets[slot]) % len(choices)]
        else:
            appearance[slot] = "none"
    return normalize_character(appearance)


def _traffic_asset(index: int) -> dict:
    eligible = [row for row in load_vehicle_catalog() if row.get("traffic_eligible")]
    if not eligible:
        return vehicle_meta(0)
    index = max(0, int(index))
    # Keep the newly generated service/heavy fleet visible alongside the
    # recently added player pixel cars in ordinary traffic.
    generated = [row for row in eligible if row.get("art_set") == "generated_vehicle_fleet_2026_08_22"]
    if generated and index % 3 == 0:
        return generated[(index // 3) % len(generated)]
    return eligible[index % len(eligible)]


def _parked_asset(index: int) -> dict:
    """Use the retained compact pixel-car fleet for curbside parking."""
    compact = [
        row for row in load_vehicle_catalog()
        if row.get("traffic_eligible")
        and str(row.get("category", "")).lower() in {"compact", "sedan", "sports", "taxi"}
        and row.get("art_set") != "generated_vehicle_fleet_2026_08_22"
    ]
    return compact[max(0, int(index)) % len(compact)] if compact else _traffic_asset(index)


def network_map_payload(map_config: dict) -> dict:
    """Return a compact JSON-safe map descriptor.

    Portable .map files use a cache-hash contract. Static data/textures are sent
    once and then loaded from each client's local cache on later connections.
    Desktop and pygbag clients ship the same compiled CSV/chunk data locally; the
    server sends only the world/chunk contract. This keeps login packet size nearly
    constant as Map 001 grows toward city scale.
    """
    if map_config.get("_portable_map_hash"):
        keys = ("id","name","description","world_w","world_h","chunked","chunk_size","chunk_cols","chunk_rows","interest_radius_chunks","server_region_chunk_cols","server_region_chunk_rows","map_build_id","default_render_mode","default_lighting_profile","street_lamps_enabled")
        out = {key: map_config.get(key) for key in keys if key in map_config}
        out["map_payload_mode"] = "portable_map_v1"
        out["map_hash"] = str(map_config.get("_portable_map_hash"))
        out["generator_version"] = str(map_config.get("_portable_generator_version", ""))
        # Global map UI needs every job destination even when static world data
        # comes from a transferred portable cache.
        out["job_locations"] = [dict(row) for row in map_config.get("job_locations", [])]
        out["parking_spots"] = [dict(row) for row in map_config.get("parking_spots", [])]
        return out

    if bool(map_config.get("chunked", False)):
        keys = (
            "id", "name", "description", "world_w", "world_h", "chunked",
            "chunk_size", "chunk_cols", "chunk_rows", "interest_radius_chunks",
            "server_region_chunk_cols", "server_region_chunk_rows",
            "map_area_multiplier", "map_build_id", "scalability_target_players", "target_player_height_px",
            "target_sedan_length_px", "target_lane_width_px", "target_sidewalk_width_px",
            "render_style", "expansion_geometry",
        )
        out = {key: map_config.get(key) for key in keys if key in map_config}
        out["map_payload_mode"] = "local_chunked_v1"
        # Traffic-light fixtures are small dynamic junction metadata, not static
        # chunk art. The client must receive the server-generated GridWorld list
        # so the synchronized states in snapshots have visible fixtures to drive.
        out["traffic_signals"] = [dict(signal) for signal in map_config.get("traffic_signals", [])]
        # The full M map is global UI and cannot infer off-interest job NPCs from
        # nearby snapshots. Publish the complete compact destination list.
        out["job_locations"] = [dict(row) for row in map_config.get("job_locations", [])]
        out["parking_spots"] = [dict(row) for row in map_config.get("parking_spots", [])]
        out.update(grid_network_metadata(map_config))
        return out

    def clean(value):
        if isinstance(value, dict):
            out = {}
            for key, item in value.items():
                if key == "building_id_by_rect" or (isinstance(key, str) and key.startswith("_")):
                    continue
                if not isinstance(key, (str, int, float, bool)) and key is not None:
                    continue
                out[key] = clean(item)
            return out
        if isinstance(value, (list, tuple)):
            return [clean(item) for item in value]
        return value
    return clean(map_config)


def server_info_payload(server_name: str, game_port: int, max_players: int, map_config: dict) -> dict:
    """Small unauthenticated status record used only by the launcher browser."""
    housing_capacity = len(blank_house_interiors(map_config))
    return {
        "protocol": DISCOVERY_MAGIC,
        "type": "server_info",
        "name": server_name,
        "port": int(game_port),
        "players": len(clients),
        "max_players": int(max_players),
        "housing_capacity": housing_capacity,
        "housing_overflow": max(0, len(clients) - housing_capacity),
        "version": SERVER_VERSION,
        "map_id": map_config["id"],
        "map_name": map_config["name"],
        "game_mode_id": ACTIVE_GAME_MODE["id"],
        "game_mode_name": ACTIVE_GAME_MODE["name"],
        "map_hash": str(map_config.get("_portable_map_hash", "")),
        "map_payload_mode": "portable_map_v1" if map_config.get("_portable_map_hash") else "local_chunked_v1",
        "traffic_cars": TRAFFIC_COUNT,
        "bicycles": len(bicycles),
        "npcs": len(npc_pedestrians),
        "server_metrics": SERVER_TICK_METRICS.public_dict(),
    }


class DiscoveryProtocol(asyncio.DatagramProtocol):
    def __init__(self, server_name: str, game_port: int, max_players: int, map_config: dict):
        self.server_name = server_name
        self.game_port = game_port
        self.max_players = max_players
        self.map_config = map_config
        self.transport: asyncio.DatagramTransport | None = None

    def connection_made(self, transport) -> None:
        self.transport = transport

    def datagram_received(self, data: bytes, addr) -> None:
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            return
        if text != DISCOVERY_MAGIC or self.transport is None:
            return
        payload = server_info_payload(self.server_name, self.game_port, self.max_players, self.map_config)
        self.transport.sendto(json.dumps(payload, separators=(",", ":")).encode("utf-8"), addr)


@dataclass
class ServerTickMetrics:
    """Rolling proof of authoritative-loop cadence and work cost."""

    configured_rate_hz: float
    window_seconds: float = 1.0
    window_started: float = field(default_factory=time.monotonic)
    window_ticks: int = 0
    window_work_seconds: float = 0.0
    window_max_work_seconds: float = 0.0
    measured_rate_hz: float = 0.0
    average_work_ms: float = 0.0
    max_work_ms: float = 0.0
    overrun_count: int = 0

    @property
    def budget_seconds(self) -> float:
        return 1.0 / max(1.0, float(self.configured_rate_hz))

    def record_tick(self, work_seconds: float, completed_at: float | None = None) -> None:
        work = max(0.0, float(work_seconds))
        now = time.monotonic() if completed_at is None else float(completed_at)
        self.window_ticks += 1
        self.window_work_seconds += work
        self.window_max_work_seconds = max(self.window_max_work_seconds, work)
        if work > self.budget_seconds:
            self.overrun_count += 1
        elapsed = now - self.window_started
        if elapsed < self.window_seconds:
            return
        self.measured_rate_hz = self.window_ticks / max(1e-6, elapsed)
        self.average_work_ms = self.window_work_seconds * 1000.0 / max(1, self.window_ticks)
        self.max_work_ms = self.window_max_work_seconds * 1000.0
        self.window_started = now
        self.window_ticks = 0
        self.window_work_seconds = 0.0
        self.window_max_work_seconds = 0.0

    def public_dict(self) -> dict:
        return {
            "server_tick_rate_hz": round(self.measured_rate_hz, 2),
            "server_tick_configured_rate_hz": round(self.configured_rate_hz, 2),
            "server_tick_time_ms": round(self.average_work_ms, 3),
            "server_tick_max_time_ms": round(self.max_work_ms, 3),
            "server_tick_budget_ms": round(self.budget_seconds * 1000.0, 3),
            "server_tick_overruns": int(self.overrun_count),
            "snapshot_rate_hz": int(SNAPSHOT_RATE),
            "ambient_sim_rate_hz": round(AMBIENT_SIM_RATE, 2),
        }


SERVER_TICK_METRICS = ServerTickMetrics(SERVER_TICK_RATE)


@dataclass
class ClientSession:
    websocket: ServerConnection
    player: PlayerState
    phone: str
    inventory: list[dict | None]
    apartment_interior_id: str = ""
    friend_names: set[str] = field(default_factory=set)
    input_x: float = 0.0
    input_y: float = 0.0
    aim: float = 0.0
    last_input_time: float = field(default_factory=time.monotonic)
    driving_vehicle_id: str = ""
    passenger_vehicle_id: str = ""
    riding_bicycle_id: str = ""
    boost: bool = False
    handbrake: bool = False
    crouch_requested: bool = False
    crouching: bool = False
    crouch_cancel_latched: bool = False
    prone: bool = False
    forced_prone_until: float = 0.0
    collision_disabled_until: float = 0.0
    stand_delay_remaining: float = 0.0
    jump_until: float = 0.0
    jump_started_at: float = 0.0
    jump_kind: str = ""
    jump_velocity_x: float = 0.0
    jump_velocity_y: float = 0.0
    last_chat_time: float = 0.0
    last_sms_time: float = 0.0
    last_bug_report_time: float = 0.0
    bug_reports_this_session: int = 0
    bug_rate_key: str = ""


def reset_on_foot_actions(session: ClientSession) -> None:
    """Clear pedestrian-only actions when entering a vehicle or interior."""
    session.crouch_requested = False
    session.crouching = False
    session.crouch_cancel_latched = False
    session.prone = False
    session.forced_prone_until = 0.0
    session.collision_disabled_until = 0.0
    session.stand_delay_remaining = 0.0
    session.jump_until = 0.0
    session.jump_started_at = 0.0
    session.jump_kind = ""
    session.jump_velocity_x = 0.0
    session.jump_velocity_y = 0.0


def request_player_prone_toggle(session: ClientSession, now: float | None = None) -> bool:
    """Apply the preview's X-to-prone/stand rule on the authoritative server."""
    timestamp = time.monotonic() if now is None else float(now)
    if timestamp < session.forced_prone_until:
        return False
    if session.jump_kind and timestamp < session.jump_until:
        return False
    session.prone = not session.prone
    session.crouching = False
    session.crouch_cancel_latched = bool(session.crouch_requested)
    session.stand_delay_remaining = 0.0
    return True


def request_player_jump(session: ClientSession, now: float | None = None) -> str:
    """Start, advance, or consume Space according to the movement-preview contract."""
    timestamp = time.monotonic() if now is None else float(now)
    if timestamp < session.forced_prone_until:
        return "ignored"
    if session.prone:
        session.prone = False
        session.crouching = False
        session.crouch_cancel_latched = bool(session.crouch_requested)
        session.stand_delay_remaining = 0.0
        return "stand"
    if session.jump_kind == "jump" and timestamp < session.jump_until:
        if timestamp - session.jump_started_at <= DOUBLE_JUMP_WINDOW_SECONDS:
            session.jump_kind = "double_jump"
            session.jump_started_at = timestamp
            session.jump_until = timestamp + DOUBLE_JUMP_DURATION_SECONDS
            speed = DOUBLE_JUMP_FORWARD_SPEED
        else:
            return "ignored"
    elif session.jump_kind and timestamp < session.jump_until:
        return "ignored"
    else:
        session.jump_kind = "jump"
        session.jump_started_at = timestamp
        session.jump_until = timestamp + JUMP_DURATION_SECONDS
        speed = JUMP_FORWARD_SPEED

    heading_x, heading_y = session.input_x, session.input_y
    length = math.hypot(heading_x, heading_y)
    if length <= 0.05:
        heading_x, heading_y = math.cos(session.aim), math.sin(session.aim)
        length = 1.0
    session.jump_velocity_x = heading_x / length * speed
    session.jump_velocity_y = heading_y / length * speed
    session.crouching = False
    session.prone = False
    session.stand_delay_remaining = 0.0
    session.boost = False
    return session.jump_kind


def finish_expired_player_jump(session: ClientSession, now: float | None = None) -> str:
    """Finish an authored jump and apply the preview's double-jump prone landing."""
    timestamp = time.monotonic() if now is None else float(now)
    if not session.jump_kind or timestamp < session.jump_until:
        return ""
    landed = session.jump_kind
    session.jump_kind = ""
    session.jump_until = 0.0
    session.jump_started_at = 0.0
    session.jump_velocity_x = 0.0
    session.jump_velocity_y = 0.0
    if landed == "double_jump":
        session.prone = True
        session.crouching = False
    return landed


def request_grid_fire_escape(session: ClientSession) -> str:
    """Use Space while stationary at a GridWorld fire escape to change levels."""
    if not GRID_RUNTIME_ACTIVE or GRID_WORLD is None:
        return ""
    if session.driving_vehicle_id or session.passenger_vehicle_id or session.riding_bicycle_id:
        return ""
    if math.hypot(session.input_x, session.input_y) > 0.05:
        return ""
    player = session.player
    transition = GRID_WORLD.fire_escape_transition(player.x, player.y, int(player.level))
    if transition is None:
        return ""
    next_level, target_x, target_y = transition
    if next_level == 1 and not GRID_WORLD.circle_roof_walkable(target_x, target_y, PLAYER_RADIUS):
        return ""
    reset_on_foot_actions(session)
    player.level = int(next_level)
    player.x, player.y = float(target_x), float(target_y)
    return "roof" if next_level == 1 else "ground"


@dataclass
class TrafficVehicle:
    vehicle_id: str
    route_index: int
    next_waypoint: int
    x: float
    y: float
    angle: float
    speed: float
    color_index: int
    sprite_index: int
    vehicle_class: str = "sedan"
    collision_length: float = 42.0
    collision_width: float = 18.0
    render_length: int = 48
    speed_factor: float = 1.0
    controlled_by: str = ""
    passenger_ids: list[str] = field(default_factory=list)
    npc_driver: bool = True
    parked: bool = False
    steering: float = 0.0
    wait_age: float = 0.0
    stuck_time: float = 0.0
    last_progress_x: float = 0.0
    last_progress_y: float = 0.0
    home_fraction: float = 0.0
    horn_until: float = 0.0
    horn_sequence: int = 0
    red_light_waiting: bool = False
    turn_signal: int = 0
    headlights: bool = False
    brake_lights: bool = False
    junction_id: str = ""
    junction_time: float = 0.0

    def public_dict(self) -> dict:
        return {
            "id": self.vehicle_id,
            "route": self.route_index,
            "x": round(self.x, 2),
            "y": round(self.y, 2),
            "angle": round(self.angle, 4),
            "speed": round(self.speed, 2),
            "color": self.color_index,
            "sprite": self.sprite_index,
            "vehicle_class": self.vehicle_class,
            "collision_length": round(self.collision_length, 1),
            "collision_width": round(self.collision_width, 1),
            "render_length": self.render_length,
            "driver": "player" if self.controlled_by else ("npc" if self.npc_driver else "none"),
            "passengers": len(self.passenger_ids),
            "passenger_capacity": PASSENGER_CAPACITY,
            "parked": bool(self.parked),
            "horn": time.monotonic() < self.horn_until,
            "horn_sequence": int(self.horn_sequence),
            "turn_signal": int(self.turn_signal),
            "headlights": bool(self.headlights),
            "brake_lights": bool(self.brake_lights),
        }


traffic_vehicles: list[TrafficVehicle] = []


def _activate_traffic_horn(car: TrafficVehicle, duration: float = 0.8) -> None:
    """Publish one durable horn event even when a snapshot misses its pulse."""
    now = time.monotonic()
    if now >= float(car.horn_until):
        car.horn_sequence += 1
    car.horn_until = max(float(car.horn_until), now + max(0.2, float(duration)))


@dataclass
class NPCPedestrian:
    npc_id: str
    route_index: int
    next_waypoint: int
    x: float
    y: float
    speed: float
    aim: float
    appearance: dict
    pause_timer: float = 0.0
    route_direction: int = 1
    step_counter: int = 0
    kind: str = "pedestrian"
    stuck_time: float = 0.0
    last_progress_x: float = 0.0
    last_progress_y: float = 0.0
    signal_waiting: bool = False
    companion_id: str = ""
    level: int = 0

    def public_dict(self) -> dict:
        payload = {
            "id": self.npc_id,
            "x": round(self.x, 2),
            "y": round(self.y, 2),
            "aim": round(self.aim, 4),
            "appearance": normalize_character(self.appearance),
            "kind": self.kind,
            "level": int(self.level),
        }
        if self.companion_id:
            payload["companion_id"] = self.companion_id
        return payload


npc_pedestrians: list[NPCPedestrian] = []


@dataclass
class BloodStain:
    stain_id: str
    x: float
    y: float
    expires_at: float

    def public_dict(self, now: float) -> dict:
        return {
            "id": self.stain_id,
            "x": round(self.x, 2),
            "y": round(self.y, 2),
            "remaining": round(max(0.0, self.expires_at - now), 2),
        }


@dataclass
class HydrantState:
    hydrant_id: str
    x: float
    y: float
    broken_until: float = 0.0
    water_until: float = 0.0

    def public_dict(self, now: float) -> dict:
        broken = self.broken_until > now
        return {
            "id": self.hydrant_id,
            "x": round(self.x, 2),
            "y": round(self.y, 2),
            "broken": broken,
            "water_remaining": round(max(0.0, self.water_until - now), 2) if broken else 0.0,
            "respawn_remaining": round(max(0.0, self.broken_until - now), 2) if broken else 0.0,
        }


@dataclass
class NPCRespawn:
    due_at: float
    route_index: int
    next_waypoint: int
    speed: float
    appearance: dict


blood_stains: list[BloodStain] = []
npc_respawns: list[NPCRespawn] = []
hydrants: dict[str, HydrantState] = {}


@dataclass
class BicycleState:
    bicycle_id: str
    route_index: int
    next_waypoint: int
    x: float
    y: float
    angle: float
    speed: float
    controlled_by: str = ""
    npc_rider: bool = False
    parked: bool = False
    appearance: dict | None = None
    wait_age: float = 0.0

    def public_dict(self) -> dict:
        return {
            "id": self.bicycle_id,
            "x": round(self.x, 2),
            "y": round(self.y, 2),
            "angle": round(self.angle, 4),
            "speed": round(self.speed, 2),
            "controlled_by": self.controlled_by,
            "rider": "player" if self.controlled_by else ("npc" if self.npc_rider else "none"),
            "parked": bool(self.parked),
            "appearance": normalize_character(self.appearance),
        }


bicycles: list[BicycleState] = []


def _offset_loop_waypoints(points: list, offset: float) -> list[list[float]]:
    if len(points) < 2 or abs(float(offset)) < 1e-6:
        return [[float(p[0]), float(p[1])] for p in points]
    out: list[list[float]] = []
    n = len(points)
    for i, p in enumerate(points):
        prev = points[(i - 1) % n]
        nxt = points[(i + 1) % n]
        dx = float(nxt[0]) - float(prev[0])
        dy = float(nxt[1]) - float(prev[1])
        mag = math.hypot(dx, dy)
        if mag < 1e-6:
            # Fallback to outgoing segment.
            dx = float(nxt[0]) - float(p[0])
            dy = float(nxt[1]) - float(p[1])
            mag = math.hypot(dx, dy)
        if mag < 1e-6:
            out.append([float(p[0]), float(p[1])])
            continue
        nx, ny = -dy / mag, dx / mag
        out.append([float(p[0]) + nx * float(offset), float(p[1]) + ny * float(offset)])
    return out


def _smooth_loop_waypoints(points: list, radius: float, samples: int = 3) -> tuple[list[list[float]], dict[int, int]]:
    """Fillet closed-route corners with a small quadratic arc.

    This is a route preprocessing cost, not a per-tick cost.  Cars get a modest
    radius and bicycles a much tighter one, allowing both to negotiate city
    corners without the old instantaneous 90-degree heading snap.
    """
    raw = [[float(p[0]), float(p[1])] for p in points]
    if len(raw) < 3 or radius <= 0.5:
        return raw, {i: i for i in range(len(raw))}
    out: list[list[float]] = []
    source_to_runtime: dict[int, int] = {}
    n = len(raw)
    samples = max(2, int(samples))
    for i, b in enumerate(raw):
        a = raw[(i - 1) % n]; c = raw[(i + 1) % n]
        inx, iny = b[0]-a[0], b[1]-a[1]
        outx, outy = c[0]-b[0], c[1]-b[1]
        lin, lout = math.hypot(inx,iny), math.hypot(outx,outy)
        if lin < 1e-6 or lout < 1e-6:
            source_to_runtime[i] = len(out); out.append(b); continue
        inx, iny = inx/lin, iny/lin; outx, outy = outx/lout, outy/lout
        dot = max(-1.0, min(1.0, inx*outx + iny*outy))
        # Straight-ish points remain untouched; this avoids needless tiny segments.
        if dot > 0.985:
            source_to_runtime[i] = len(out); out.append(b); continue
        cut = min(float(radius), lin*0.30, lout*0.30)
        entry = [b[0]-inx*cut, b[1]-iny*cut]
        exitp = [b[0]+outx*cut, b[1]+outy*cut]
        source_to_runtime[i] = len(out)  # red lights stop at the curve entry.
        out.append(entry)
        for j in range(1, samples+1):
            t = j / samples
            omt = 1.0-t
            qx = omt*omt*entry[0] + 2*omt*t*b[0] + t*t*exitp[0]
            qy = omt*omt*entry[1] + 2*omt*t*b[1] + t*t*exitp[1]
            out.append([qx,qy])
    return out, source_to_runtime


def _prepare_runtime_routes(routes: list[dict], default_turn_radius: float = 0.0) -> None:
    for route in routes:
        points = route.get("waypoints", []) or []
        try:
            offset = float(route.get("lane_offset", 0.0))
        except (TypeError, ValueError):
            offset = 0.0
        offset_points = _offset_loop_waypoints(points, offset)
        try:
            radius = float(route.get("turn_radius", default_turn_radius))
        except (TypeError, ValueError):
            radius = float(default_turn_radius)
        runtime, source_map = _smooth_loop_waypoints(offset_points, radius, 3)
        route["_runtime_waypoints"] = runtime
        if route.get("signals"):
            route["_runtime_signals"] = {
                str(source_map.get(int(src), int(src))): phase
                for src, phase in route.get("signals", {}).items()
            }


def _route_points(route: dict) -> list:
    return route.get("_runtime_waypoints") or route.get("waypoints", []) or []


def _sample_route(route: dict, fraction: float) -> tuple[float, float, int, float]:
    """Resolve one authored route fraction without changing the authored value.

    v2.1 treats fixed start tables as executable map data. Values outside [0, 1)
    are map-authoring errors and must not be silently wrapped with modulo math.
    """
    points = _route_points(route)
    if len(points) < 2:
        return 0.0, 0.0, 0, 0.0
    fraction = float(fraction)
    if not 0.0 <= fraction < 1.0:
        raise ValueError(f"start_fraction must be in [0,1), got {fraction!r} for route {route.get('id','?')}")
    lengths: list[float] = []
    total = 0.0
    for i, a in enumerate(points):
        b = points[(i + 1) % len(points)]
        length = math.hypot(float(b[0]) - float(a[0]), float(b[1]) - float(a[1]))
        lengths.append(length)
        total += length
    remaining = fraction * total
    for i, length in enumerate(lengths):
        if remaining <= length or i == len(lengths) - 1:
            a = points[i]
            b = points[(i + 1) % len(points)]
            t = 0.0 if length <= 0 else remaining / length
            x = float(a[0]) + (float(b[0]) - float(a[0])) * t
            y = float(a[1]) + (float(b[1]) - float(a[1])) * t
            angle = math.atan2(float(b[1]) - float(a[1]), float(b[0]) - float(a[0]))
            return x, y, (i + 1) % len(points), angle
        remaining -= length
    a = points[0]
    b = points[1]
    return float(a[0]), float(a[1]), 1, math.atan2(float(b[1])-float(a[1]), float(b[0])-float(a[0]))


def _fixed_start_plan(routes: list[dict], starts: list[dict], *, limit: int | None = None) -> list[tuple[dict, dict, int, float, float, int, float]]:
    """Resolve ordered CSV start rows into one deterministic runtime plan.

    Route choice and start choice happen only in authored CSV data. This helper is
    intentionally boring: preserve row order, look up the named route, sample the
    authored fraction, and return it. No weighting, random selection, fallback
    route, or generated start position exists here.
    """
    if limit is None:
        selected = starts
    else:
        selected = starts[:max(0, min(int(limit), len(starts)))]
    route_by_id = {str(route.get("id", "")): i for i, route in enumerate(routes)}
    plan: list[tuple[dict, dict, int, float, float, int, float]] = []
    for start in selected:
        route_id = str(start.get("route_id", ""))
        if route_id not in route_by_id:
            raise ValueError(f"fixed AI start {start.get('id','?')} references unknown route {route_id!r}")
        route_index = route_by_id[route_id]
        route = routes[route_index]
        fraction = float(start.get("start_fraction", 0.0))
        x, y, next_waypoint, angle = _sample_route(route, fraction)
        plan.append((start, route, route_index, x, y, next_waypoint, angle))
    return plan


def _nearest_route_heading(x: float, y: float, routes: list[dict], max_distance: float = 240.0) -> float | None:
    """Return the tangent of the closest traffic-route segment near a spawn.

    Parked/imported spawns can inherit arbitrary source-polyline angles. Aligning them
    to the nearest driveable route prevents cars from beginning diagonally across a
    lane or curb while preserving explicitly remote/off-road spawns.
    """
    best_distance = float("inf")
    best_heading: float | None = None
    for route in routes:
        points = _route_points(route)
        if len(points) < 2:
            continue
        for a, b in zip(points, points[1:] + points[:1]):
            ax, ay = float(a[0]), float(a[1]); bx, by = float(b[0]), float(b[1])
            dx, dy = bx - ax, by - ay
            denom = dx * dx + dy * dy
            if denom <= 1e-9:
                continue
            u = max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / denom))
            qx, qy = ax + u * dx, ay + u * dy
            distance = math.hypot(x - qx, y - qy)
            if distance < best_distance:
                best_distance = distance
                best_heading = math.atan2(dy, dx)
    return best_heading if best_distance <= max_distance else None


def initialize_traffic(count: int) -> None:
    """Create moving traffic directly from fixed CSV route/start assignments.

    No random route selection, weighted choice, rejection sampling, or random start
    offset occurs here.  `traffic_starts.csv` is the complete spawn plan.
    """
    traffic_vehicles.clear()
    routes = ACTIVE_MAP.get("traffic_routes", []) or []
    starts = ACTIVE_MAP.get("traffic_starts", []) or []
    if not routes or not starts or count <= 0:
        return
    _prepare_runtime_routes(routes, 34.0)
    if int(count) > len(starts):
        print(f"Traffic request {count} capped to {len(starts)} fixed traffic_starts.csv slots.", flush=True)

    for i, (start, route, route_index, x, y, next_waypoint, angle) in enumerate(_fixed_start_plan(routes, starts, limit=count)):
        fraction = float(start.get("start_fraction", 0.0))
        meta = _traffic_asset(int(start.get("asset_index", i)))
        collision_length = max(28.0, float(meta.get("collision_length", 42.0)) * 1.18)
        collision_width = max(16.0, float(meta.get("collision_width", 18.0)) * 1.14)
        speed_factor = max(0.45, min(1.15, float(meta.get("speed_factor", 1.0)) * float(start.get("speed_scale", 1.0))))
        limit = float(route.get("speed_limit", 150.0))
        traffic_vehicles.append(TrafficVehicle(
            vehicle_id=str(start.get("id", f"car{i+1:03d}")), route_index=route_index, next_waypoint=next_waypoint,
            x=x, y=y, angle=angle, speed=limit * 0.72 * speed_factor, color_index=i % len(TRAFFIC_CAR_COLORS),
            sprite_index=int(meta.get("index", 0)), vehicle_class=str(meta.get("category", "sedan")),
            collision_length=collision_length, collision_width=collision_width,
            render_length=max(24, int(meta.get("render_length", 48))), speed_factor=speed_factor,
            controlled_by="", npc_driver=True, parked=False,
            last_progress_x=x, last_progress_y=y, home_fraction=fraction,
        ))


def initialize_parked_vehicles() -> None:
    spawns = ACTIVE_MAP.get("parked_vehicle_spawns", []) or []
    if not spawns:
        return
    routes = ACTIVE_MAP.get("traffic_routes", []) or []
    _prepare_runtime_routes(routes, 34.0)
    base = len(traffic_vehicles)
    for i, spawn in enumerate(spawns):
        if not isinstance(spawn, (list, tuple)) or len(spawn) < 2:
            continue
        meta = _parked_asset(i)
        x, y = float(spawn[0]), float(spawn[1])
        angle = float(spawn[2]) if len(spawn) >= 3 else 0.0
        route_heading = _nearest_route_heading(x, y, routes)
        if route_heading is not None:
            # Parallel rather than perpendicular alignment is the important invariant.
            # Preserve the spawn's intended travel direction when it is already close.
            opposite = (route_heading + math.pi) % (2.0 * math.pi)
            delta_a = abs((angle - route_heading + math.pi) % (2.0 * math.pi) - math.pi)
            delta_b = abs((angle - opposite + math.pi) % (2.0 * math.pi) - math.pi)
            angle = route_heading if delta_a <= delta_b else opposite
        traffic_vehicles.append(TrafficVehicle(
            vehicle_id=f"parked{base+i+1:03d}", route_index=-1, next_waypoint=0,
            x=x, y=y, angle=angle, speed=0.0, color_index=(base+i) % len(TRAFFIC_CAR_COLORS),
            sprite_index=int(meta.get("index", 0)), vehicle_class=str(meta.get("category", "sedan")),
            collision_length=max(28.0, float(meta.get("collision_length", 42.0)) * 1.18),
            collision_width=max(16.0, float(meta.get("collision_width", 18.0)) * 1.14),
            render_length=max(24, int(meta.get("render_length", 48))),
            speed_factor=max(0.45, min(1.15, float(meta.get("speed_factor", 1.0)))),
            controlled_by="", npc_driver=False, parked=True,
            last_progress_x=x, last_progress_y=y,
        ))


def initialize_bicycles() -> None:
    bicycles.clear()
    routes = ACTIVE_MAP.get("bicycle_routes", []) or []
    starts = ACTIVE_MAP.get("bicycle_starts", []) or []
    _prepare_runtime_routes(routes, 14.0)
    ai_speed = float(BICYCLE_AI.get("ai_speed_px_s", 112.0))
    bike_id = 1
    for start, route, route_index, x, y, next_wp, heading in _fixed_start_plan(routes, starts):
        appearance = _indexed_character_appearance(int(start.get("appearance_index", bike_id-1)), preset_only=True)
        bike=BicycleState(
            bicycle_id=str(start.get("id", f"bike{bike_id:03d}")), route_index=route_index, next_waypoint=next_wp,
            x=x, y=y, angle=heading, speed=float(route.get("speed", ai_speed)) * float(start.get("speed_scale", 1.0)),
            npc_rider=True, parked=False, appearance=appearance,
        )
        # CSV starts are preferences, never permission to spawn over water or
        # inside a car/building. Search the same deterministic loop for safety.
        if _bicycle_map_blocked(bike,bike.x,bike.y,bike.angle) or _bicycle_hits_vehicle(bike,bike.x,bike.y,bike.angle):
            points=_route_points(route)
            rescued=False
            for wp,(px,py) in enumerate(points):
                qx,qy=points[(wp+1)%len(points)]
                candidate_angle=math.atan2(float(qy)-float(py),float(qx)-float(px))
                if not _bicycle_map_blocked(bike,float(px),float(py),candidate_angle) and not _bicycle_hits_vehicle(bike,float(px),float(py),candidate_angle):
                    bike.x,bike.y,bike.angle=float(px),float(py),candidate_angle
                    bike.next_waypoint=(wp+1)%len(points);rescued=True;break
            if not rescued:
                continue
        bicycles.append(bike)
        bike_id += 1

    max_parked = max(0, int(BICYCLE_AI.get("parked_bikes", 8)))
    for i, spawn in enumerate((ACTIVE_MAP.get("parked_bicycle_spawns", []) or [])[:max_parked]):
        if not isinstance(spawn, (list, tuple)) or len(spawn) < 2:
            continue
        bike=BicycleState(
            bicycle_id=f"parkedbike{i+1:03d}", route_index=-1, next_waypoint=0,
            x=float(spawn[0]), y=float(spawn[1]), angle=float(spawn[2]) if len(spawn) >= 3 else 0.0,
            speed=0.0, npc_rider=False, parked=True, appearance=normalize_character(None),
        )
        if not _bicycle_map_blocked(bike,bike.x,bike.y,bike.angle) and not _bicycle_hits_vehicle(bike,bike.x,bike.y,bike.angle):
            bicycles.append(bike)


def _bicycle_grid() -> dict[tuple[int, int], list]:
    return build_spatial_grid(bicycles, 128.0)


def update_bicycles(dt: float, sessions: list[ClientSession]) -> None:
    routes = ACTIVE_MAP.get("bicycle_routes", []) or []
    if not bicycles:
        return
    car_grid = _traffic_grid(traffic_vehicles) if traffic_vehicles else {}
    for bike in bicycles:
        if bike.controlled_by or bike.parked or bike.route_index < 0 or not bike.npc_rider:
            continue
        if not (0 <= bike.route_index < len(routes)):
            continue
        points = _route_points(routes[bike.route_index])
        if len(points) < 2:
            continue
        tx, ty = points[bike.next_waypoint % len(points)]
        dx, dy = float(tx) - bike.x, float(ty) - bike.y
        dist = math.hypot(dx, dy)
        if dist <= 5.0:
            bike.next_waypoint = (bike.next_waypoint + 1) % len(points)
            tx, ty = points[bike.next_waypoint]
            dx, dy = float(tx) - bike.x, float(ty) - bike.y
            dist = math.hypot(dx, dy)
        if dist < 1e-6:
            continue
        heading = math.atan2(dy, dx)
        hx, hy = math.cos(heading), math.sin(heading)
        desired = float(routes[bike.route_index].get("speed", BICYCLE_AI.get("ai_speed_px_s", 112.0)))

        # Yield to cars crossing or occupying the bike lane ahead.
        for car in nearby_at(bike.x, bike.y, car_grid, float(TRAFFIC_SPATIAL_CELL), 1):
            rx, ry = car.x - bike.x, car.y - bike.y
            forward = rx * hx + ry * hy
            lateral = abs(rx * hy - ry * hx)
            if 0.0 < forward < 70.0 and lateral < 28.0:
                desired = min(desired, max(0.0, car.speed - 18.0))

        # Yield to players standing/riding directly ahead rather than clipping them.
        for session in sessions:
            rx, ry = session.player.x - bike.x, session.player.y - bike.y
            forward = rx * hx + ry * hy
            lateral = abs(rx * hy - ry * hx)
            if 0.0 < forward < 50.0 and lateral < 20.0:
                desired = 0.0
                break

        accel = 110.0 if desired > bike.speed else 190.0
        if bike.speed < desired:
            bike.speed = min(desired, bike.speed + accel * dt)
        else:
            bike.speed = max(desired, bike.speed - accel * dt)
        move = min(dist, bike.speed * dt)
        nx,ny=bike.x+hx*move,bike.y+hy*move
        if _bicycle_map_blocked(bike,nx,ny,heading) or _bicycle_hits_vehicle(bike,nx,ny,heading):
            bike.speed=0.0
        else:
            bike.x,bike.y,bike.angle=nx,ny,heading


def nearest_bicycle(x: float, y: float, radius: float = 82.0) -> BicycleState | None:
    best = None
    best_d = float(radius)
    for bike in bicycles:
        d = math.hypot(bike.x - x, bike.y - y)
        if d <= best_d:
            best = bike
            best_d = d
    return best


def _traffic_should_yield_to_player(car: TrafficVehicle, target: tuple[float, float], sessions: list[ClientSession]) -> bool:
    dx = target[0] - car.x
    dy = target[1] - car.y
    mag = math.hypot(dx, dy)
    if mag < 1e-6:
        return False
    hx, hy = dx / mag, dy / mag
    now = time.monotonic()
    for session in sessions:
        if now < float(session.collision_disabled_until):
            continue
        rx = session.player.x - car.x
        ry = session.player.y - car.y
        forward = rx * hx + ry * hy
        lateral = abs(rx * hy - ry * hx)
        if 0.0 < forward < TRAFFIC_PEDESTRIAN_YIELD_DISTANCE and lateral < 28.0:
            return True
    return False


def _traffic_should_yield_to_pedestrian(car: TrafficVehicle, heading: float) -> bool:
    """Brake for a pedestrian ahead and expose a short horn signal."""
    hx, hy = math.cos(heading), math.sin(heading)
    for npc in npc_pedestrians:
        # Sidewalk crowds—including pedestrians passing below overhead lamps—
        # are not lane hazards. Yield only after a pedestrian has legally
        # entered the road/crosswalk, preventing curb queues from starving a
        # green vehicle phase (#149/#171).
        if GRID_WORLD is not None and GRID_WORLD.collision_at("ground", npc.x, npc.y) != "road":
            continue
        rx, ry = npc.x - car.x, npc.y - car.y
        forward = rx * hx + ry * hy
        lateral = abs(rx * hy - ry * hx)
        if 0.0 < forward < 145.0 and lateral < car.collision_width * 0.5 + 24.0:
            return True
    return False


def _traffic_grid(vehicles: list[TrafficVehicle]) -> dict[tuple[int, int], list[TrafficVehicle]]:
    """Cheap spatial hash used for car following and collision avoidance."""
    grid: dict[tuple[int, int], list[TrafficVehicle]] = {}
    cell = float(TRAFFIC_SPATIAL_CELL)
    for car in vehicles:
        key = (int(car.x // cell), int(car.y // cell))
        grid.setdefault(key, []).append(car)
    return grid


def _nearby_cars(car: TrafficVehicle, grid: dict[tuple[int, int], list[TrafficVehicle]]) -> list[TrafficVehicle]:
    cell = float(TRAFFIC_SPATIAL_CELL)
    cx, cy = int(car.x // cell), int(car.y // cell)
    out: list[TrafficVehicle] = []
    for yy in range(cy - 1, cy + 2):
        for xx in range(cx - 1, cx + 2):
            out.extend(grid.get((xx, yy), ()))
    return out


def _oriented_boxes_overlap(
    ax: float, ay: float, a_angle: float, a_length: float, a_width: float,
    bx: float, by: float, b_angle: float, b_length: float, b_width: float,
) -> bool:
    """Separating-axis test for two center-positioned rotated rectangles."""
    af = (math.cos(a_angle), math.sin(a_angle))
    aside = (-af[1], af[0])
    bf = (math.cos(b_angle), math.sin(b_angle))
    bside = (-bf[1], bf[0])
    ahl, ahw = max(1.0, a_length * 0.5), max(1.0, a_width * 0.5)
    bhl, bhw = max(1.0, b_length * 0.5), max(1.0, b_width * 0.5)
    dx, dy = bx - ax, by - ay
    for axis in (af, aside, bf, bside):
        center_gap = abs(dx * axis[0] + dy * axis[1])
        a_radius = ahl * abs(af[0] * axis[0] + af[1] * axis[1]) + ahw * abs(aside[0] * axis[0] + aside[1] * axis[1])
        b_radius = bhl * abs(bf[0] * axis[0] + bf[1] * axis[1]) + bhw * abs(bside[0] * axis[0] + bside[1] * axis[1])
        if center_gap >= a_radius + b_radius:
            return False
    return True


def _bicycle_dimensions() -> tuple[float,float]:
    return (
        max(18.0,float(BICYCLE_AI.get("collision_length_px",42.0))),
        max(8.0,float(BICYCLE_AI.get("collision_width_px",18.0))),
    )


def _bicycle_map_blocked(bike: BicycleState, x: float, y: float, angle: float) -> bool:
    """Test the complete compact bicycle body against world, water and buildings."""
    length,width=_bicycle_dimensions();hl,hw=length*.5,width*.5
    ca,sa=math.cos(angle),math.sin(angle)
    extent_x=abs(ca)*hl+abs(sa)*hw;extent_y=abs(sa)*hl+abs(ca)*hw
    world_w=float(ACTIVE_MAP.get("world_w",0.0));world_h=float(ACTIVE_MAP.get("world_h",0.0))
    if x-extent_x<=0 or y-extent_y<=0 or x+extent_x>=world_w or y+extent_y>=world_h:
        return True
    samples=[(x,y),(x+ca*hl,y+sa*hl),(x-ca*hl,y-sa*hl),
        (x-sa*hw,y+ca*hw),(x+sa*hw,y-ca*hw),
        (x+ca*hl-sa*hw,y+sa*hl+ca*hw),(x+ca*hl+sa*hw,y+sa*hl-ca*hw),
        (x-ca*hl-sa*hw,y-sa*hl+ca*hw),(x-ca*hl+sa*hw,y-sa*hl-ca*hw)]
    for px,py in samples:
        if point_in_water(px,py,ACTIVE_MAP) and not point_near_road(px,py,ACTIVE_MAP,extra=0.0,bridge_only=True,level=0):
            return True
    rects=collision_buildings_near(x,y,ACTIVE_MAP) if ACTIVE_MAP.get("chunked") else ACTIVE_MAP.get("buildings",[])
    return any(_oriented_boxes_overlap(x,y,angle,length,width,float(rx)+float(rw)*.5,float(ry)+float(rh)*.5,0.0,float(rw),float(rh)) for rx,ry,rw,rh in rects)


def _bicycle_hits_vehicle(bike: BicycleState, x: float, y: float, angle: float) -> bool:
    length,width=_bicycle_dimensions()
    for car in traffic_vehicles:
        if _oriented_boxes_overlap(x,y,angle,length,width,car.x,car.y,car.angle,car.collision_length,car.collision_width):
            return True
    return False


def _vehicle_hits_bicycle(car: TrafficVehicle, x: float, y: float, angle: float) -> bool:
    length,width=_bicycle_dimensions()
    for bike in bicycles:
        if _oriented_boxes_overlap(x,y,angle,car.collision_length,car.collision_width,bike.x,bike.y,bike.angle,length,width):
            return True
    return False


def _front_axle_rotated_center(car: TrafficVehicle, proposed_angle: float) -> tuple[float, float]:
    """Return the body centre after rotating around the configured front axle."""
    axle_ratio = max(
        0.05,
        min(0.49, float(VEHICLE_SETTINGS.get("player_front_axle_offset_ratio", 0.36))),
    )
    axle_offset = car.collision_length * axle_ratio
    axle_x = car.x + math.cos(car.angle) * axle_offset
    axle_y = car.y + math.sin(car.angle) * axle_offset
    return (
        axle_x - math.cos(proposed_angle) * axle_offset,
        axle_y - math.sin(proposed_angle) * axle_offset,
    )


def _player_collision_deflection_angle(old_angle: float, requested_offset: float, direction: float) -> float:
    """Apply a small collision glance without allowing a visible heading spin."""
    limit = math.radians(4.0)
    bounded = max(-limit, min(limit, float(requested_offset) * float(direction)))
    return float(old_angle) + bounded


def _bounded_traffic_heading(car: TrafficVehicle, desired: float, dt: float) -> float:
    """Steer toward a route heading without allowing recovery snap-spins."""
    rates = {
        "bus": 0.62, "large_truck": 0.52, "tanker": 0.48,
        "truck": 0.78, "limo": 0.76, "van": 0.92, "pickup": 1.0,
    }
    rate = rates.get(str(car.vehicle_class).lower(), 1.28)
    delta = math.atan2(math.sin(desired - car.angle), math.cos(desired - car.angle))
    limit = max(math.radians(1.0), rate * max(0.0, float(dt)))
    return car.angle + max(-limit, min(limit, delta))


def _traffic_footprints_conflict(
    car: TrafficVehicle, x: float, y: float, heading: float,
    other: TrafficVehicle, ox: float, oy: float, other_heading: float,
    *, courtesy_scale: float = 1.0,
) -> bool:
    """Use both cars' rotated rectangular body boundaries for reservation."""
    return _oriented_boxes_overlap(
        x, y, heading,
        car.collision_length * courtesy_scale,
        car.collision_width * courtesy_scale,
        ox, oy, other_heading,
        other.collision_length * courtesy_scale,
        other.collision_width * courtesy_scale,
    )


def _traffic_priority(car: TrafficVehicle, target: tuple[float, float] | None = None) -> float:
    """Fair right-of-way score. Waiting cars eventually outrank fresh arrivals."""
    cap = float(TRAFFIC_AI.get("max_wait_priority", 15.0))
    gain = float(TRAFFIC_AI.get("wait_priority_gain", 1.0))
    score = min(cap, max(0.0, car.wait_age) * gain)
    if target is not None:
        score += max(0.0, 2.0 - math.hypot(target[0] - car.x, target[1] - car.y) / 90.0)
    # Stable tiny tie breaker prevents oscillating decisions.
    score += (sum(ord(ch) for ch in car.vehicle_id) % 17) * 0.001
    return score


def _traffic_junction_at(x: float, y: float, margin: float = 0.0) -> str:
    """Return the exact GridWorld junction containing a vehicle center."""
    for junction in ACTIVE_MAP.get("traffic_junctions", []) or []:
        rect = junction.get("rect", []) or []
        if len(rect) < 4:
            continue
        x0, y0, x1, y1 = map(float, rect[:4])
        reserve = max(0.0, float(margin))
        if x0 - reserve <= float(x) <= x1 + reserve and y0 - reserve <= float(y) <= y1 + reserve:
            return str(junction.get("id", ""))
    return ""


def _far_from_all_players(x: float, y: float, sessions: list[ClientSession], clearance: float) -> bool:
    r2 = float(clearance) ** 2
    return all((s.player.x - x) ** 2 + (s.player.y - y) ** 2 >= r2 for s in sessions)


def _try_recycle_stuck_car(car: TrafficVehicle, routes: list[dict], sessions: list[ClientSession]) -> bool:
    """Reset an off-screen stuck car to its own fixed CSV start slot."""
    threshold = float(TRAFFIC_AI.get("stuck_recycle_seconds", 10.0))
    clearance = float(TRAFFIC_AI.get("recycle_player_clearance_px", 900.0))
    if car.stuck_time < threshold or car.controlled_by or car.parked or car.route_index < 0:
        return False
    if not _far_from_all_players(car.x, car.y, sessions, clearance):
        return False
    route = routes[car.route_index % len(routes)]
    x, y, next_wp, angle = _sample_route(route, car.home_fraction)
    if not _far_from_all_players(x, y, sessions, clearance * 0.7):
        return False
    for other in traffic_vehicles:
        if other is car:
            continue
        sep = max(TRAFFIC_MIN_SEPARATION, 0.45 * (car.collision_length + other.collision_length))
        if (other.x - x) ** 2 + (other.y - y) ** 2 < sep * sep:
            return False
    car.x, car.y, car.next_waypoint, car.angle = x, y, next_wp, angle
    car.speed = float(route.get("speed_limit", 120.0)) * 0.45 * car.speed_factor
    car.wait_age = 0.0
    car.stuck_time = 0.0
    car.last_progress_x, car.last_progress_y = x, y
    return True


def _recover_visible_stall(car: TrafficVehicle, route: dict) -> bool:
    """Resolve a local AI deadlock without teleporting a car out of view."""
    points = _route_points(route)
    if len(points) < 2:
        return False
    current_junction = _traffic_junction_at(car.x, car.y)
    for advance in range(1, min(7, len(points))):
        next_wp = (car.next_waypoint + advance) % len(points)
        tx, ty = map(float, points[next_wp])
        # A stalled junction occupant targets the first point beyond the box,
        # so recovery clears the conflict area instead of orbiting its center.
        if current_junction and _traffic_junction_at(tx, ty) == current_junction:
            continue
        heading = math.atan2(ty - car.y, tx - car.x)
        nx = car.x + math.cos(heading) * 12.0
        ny = car.y + math.sin(heading) * 12.0
        if _vehicle_map_blocked(car, nx, ny, heading):
            continue
        car.x, car.y, car.angle = nx, ny, heading
        car.next_waypoint = next_wp
        car.speed = max(28.0, float(route.get("speed_limit", 120.0)) * 0.34 * car.speed_factor)
        car.wait_age = 0.0
        car.stuck_time = 0.0
        car.last_progress_x, car.last_progress_y = nx, ny
        return True
    return False


def update_traffic(dt: float, sessions: list[ClientSession], server_time: float) -> None:
    """Advance civilian traffic with inexpensive server-authoritative avoidance.

    A spatial hash avoids O(N^2) all-car scans and limits perception to nearby
    vehicles, braking distance governs following, and a deterministic proposed-
    position pass prevents sprite footprints from overlapping at intersections.
    """
    routes = ACTIVE_MAP.get("traffic_routes", [])
    if not routes:
        return

    grid = _traffic_grid(traffic_vehicles)
    proposals: dict[str, tuple[float, float, float, float, int, tuple[float, float], bool]] = {}

    # Phase 1: calculate speed and proposed positions from the same world state.
    for car in traffic_vehicles:
        # Player-driven and parked cars are obstacles for AI, but are not advanced
        # by the civilian route follower.
        if car.controlled_by or car.parked or car.route_index < 0:
            proposals[car.vehicle_id] = (car.x, car.y, car.angle, car.speed, car.next_waypoint, (car.x, car.y), False)
            continue
        route = routes[car.route_index % len(routes)]
        points = _route_points(route)
        if not points:
            continue
        target_raw = points[car.next_waypoint % len(points)]
        target = (float(target_raw[0]), float(target_raw[1]))
        dx, dy = target[0] - car.x, target[1] - car.y
        dist = math.hypot(dx, dy)
        next_waypoint = car.next_waypoint
        # Three pixels was much smaller than a real car's turning circle. A car
        # that passed just outside that pin-point target would circle it forever
        # (#174). Consume nearby curve samples using a body/fillet-sized radius.
        waypoint_reach = max(
            24.0,
            min(72.0, max(car.collision_length * 0.72, float(route.get("turn_radius", 34.0)) * 0.68)),
        )
        for _ in range(min(4, len(points))):
            if dist >= waypoint_reach:
                break
            # Do not mutate yet; keep the whole update two-phase.
            next_waypoint = (next_waypoint + 1) % len(points)
            target_raw = points[next_waypoint]
            target = (float(target_raw[0]), float(target_raw[1]))
            dx, dy = target[0] - car.x, target[1] - car.y
            dist = math.hypot(dx, dy)

        desired = float(route.get("speed_limit", 150.0)) * car.speed_factor
        current_junction = _traffic_junction_at(car.x, car.y)
        if current_junction:
            # Keep the conflict box flowing: a reserved occupant clears at a
            # modestly elevated crossing speed and never loiters in the middle.
            desired *= 1.22
        phase = route.get("_runtime_signals", route.get("signals", {})).get(str(next_waypoint))
        # Once a vehicle has entered, it must clear the junction without
        # stopping for the next signal phase (reports #167/#171).
        red_light = not current_junction and phase is not None and not traffic_phase_green(int(phase), server_time)
        # Start braking before the curve entry rather than waiting until the car
        # body is already in the junction. The stopping envelope scales with the
        # live speed and vehicle length.
        signal_stop_distance = max(
            150.0,
            (car.speed * car.speed) / max(1.0, 2.0 * TRAFFIC_BRAKE_DECEL)
            + car.collision_length * 0.5 + 34.0,
        )
        if red_light and dist < signal_stop_distance:
            desired = 0.0

        desired_heading = math.atan2(dy, dx) if dist > 1e-6 else car.angle
        turn_delta = math.atan2(math.sin(desired_heading - car.angle), math.cos(desired_heading - car.angle))
        car.turn_signal = -1 if turn_delta < -0.18 else (1 if turn_delta > 0.18 else 0)
        car.headlights = True
        heading = _bounded_traffic_heading(car, desired_heading, dt)
        hx, hy = math.cos(heading), math.sin(heading)
        # Physically motivated but deliberately conservative lookahead.
        braking_distance = (car.speed * car.speed) / max(1.0, 2.0 * TRAFFIC_BRAKE_DECEL)
        lookahead = max(TRAFFIC_LOOKAHEAD_MIN, braking_distance + TRAFFIC_FOLLOW_DISTANCE)

        for other in _nearby_cars(car, grid):
            if other is car:
                continue
            rx, ry = other.x - car.x, other.y - car.y
            forward = rx * hx + ry * hy
            lateral = abs(rx * hy - ry * hx)
            lane_width = (car.collision_width + other.collision_width) * 0.5 + 8.0
            if 0.0 < forward < lookahead and lateral < lane_width:
                # Vehicle dimensions matter: buses/trucks reserve more longitudinal space.
                body_gap = (car.collision_length + other.collision_length) * 0.5
                safe_gap = max(TRAFFIC_MIN_SEPARATION, body_gap + 14.0) + max(0.0, car.speed) * float(TRAFFIC_AI.get("follow_time_seconds", 0.18))
                if forward <= safe_gap:
                    desired = 0.0
                else:
                    gap_scale = min(1.0, (forward - safe_gap) / max(1.0, TRAFFIC_FOLLOW_DISTANCE))
                    desired = min(desired, max(0.0, other.speed * gap_scale + 24.0 * gap_scale))

        if _traffic_should_yield_to_player(car, target, sessions):
            desired = 0.0
        if _traffic_should_yield_to_pedestrian(car, heading):
            desired = 0.0
            _activate_traffic_horn(car, 0.8)

        car.brake_lights = desired + 2.0 < car.speed
        accel = 95.0 if desired > car.speed else TRAFFIC_BRAKE_DECEL
        speed = min(desired, car.speed + accel * dt) if car.speed < desired else max(desired, car.speed - accel * dt)
        move = min(dist, speed * dt)
        if red_light and dist <= 18.0:
            move = 0.0
            speed = 0.0
        nx = car.x + hx * move
        ny = car.y + hy * move
        proposals[car.vehicle_id] = (nx, ny, heading, speed, next_waypoint, target, red_light)

    # Phase 2: collision reservation. Nearby proposed footprints may not overlap.
    # Same-route cars give priority to the car closer to the waypoint; crossing
    # routes use stable vehicle IDs so every server tick makes the same decision.
    prop_grid: dict[tuple[int, int], list[TrafficVehicle]] = {}
    cell = float(TRAFFIC_SPATIAL_CELL)
    for car in traffic_vehicles:
        if car.vehicle_id not in proposals:
            continue
        nx, ny, *_ = proposals[car.vehicle_id]
        prop_grid.setdefault((int(nx // cell), int(ny // cell)), []).append(car)

    cancelled: set[str] = set()
    # A junction may accept only one new vehicle at a time. Existing occupants
    # keep the reservation until clear; otherwise the longest-waiting entrant
    # wins. This prevents a fresh pileup from being created several body lengths
    # inside an intersection.
    occupants: dict[str, list[TrafficVehicle]] = {}
    entrants: dict[str, list[TrafficVehicle]] = {}
    for car in traffic_vehicles:
        prop = proposals.get(car.vehicle_id)
        if prop is None or car.controlled_by or car.parked or car.route_index < 0:
            continue
        current = _traffic_junction_at(car.x, car.y)
        proposed = _traffic_junction_at(
            prop[0], prop[1],
            margin=max(20.0, float(car.collision_length) * 0.58),
        )
        if current:
            occupants.setdefault(current, []).append(car)
        elif proposed:
            entrants.setdefault(proposed, []).append(car)
    for junction_id, waiting in entrants.items():
        if occupants.get(junction_id):
            cancelled.update(car.vehicle_id for car in waiting)
            continue
        winner = max(waiting, key=lambda car: _traffic_priority(car, proposals[car.vehicle_id][5]))
        cancelled.update(car.vehicle_id for car in waiting if car is not winner)
    # Cars reserve against the complete bicycle body as well as other cars.
    # Bicycles may overlap one another, but a car and bicycle never share space.
    for car in traffic_vehicles:
        prop=proposals.get(car.vehicle_id)
        if prop is None or car.controlled_by or car.parked or car.route_index<0:
            continue
        if _vehicle_hits_bicycle(car,prop[0],prop[1],prop[2]):
            cancelled.add(car.vehicle_id)
    checked: set[tuple[str, str]] = set()
    for car in traffic_vehicles:
        prop = proposals.get(car.vehicle_id)
        if prop is None:
            continue
        nx, ny, _, _, next_wp, target, _ = prop
        cx, cy = int(nx // cell), int(ny // cell)
        candidates: list[TrafficVehicle] = []
        for yy in range(cy - 1, cy + 2):
            for xx in range(cx - 1, cx + 2):
                candidates.extend(prop_grid.get((xx, yy), ()))
        for other in candidates:
            if other is car or other.vehicle_id not in proposals:
                continue
            pair = tuple(sorted((car.vehicle_id, other.vehicle_id)))
            if pair in checked:
                continue
            checked.add(pair)
            onx, ony, _, _, other_wp, other_target, _ = proposals[other.vehicle_id]
            # Conservative center-radius reservation using each sprite class footprint.
            # This stays cheap while making buses, limos and trucks keep larger gaps.
            other_heading = proposals[other.vehicle_id][2]
            if not _traffic_footprints_conflict(car, nx, ny, prop[2], other, onx, ony, other_heading):
                continue

            car_static = bool(car.parked or car.controlled_by or car.route_index < 0)
            other_static = bool(other.parked or other.controlled_by or other.route_index < 0)
            if car_static and not other_static:
                loser = other
            elif other_static and not car_static:
                loser = car
            elif _traffic_junction_at(car.x, car.y) and not _traffic_junction_at(other.x, other.y):
                loser = other
            elif _traffic_junction_at(other.x, other.y) and not _traffic_junction_at(car.x, car.y):
                loser = car
            else:
                # Fair right-of-way: a car that has waited longer eventually wins,
                # preventing deterministic circular-yield deadlocks at intersections.
                score_car = _traffic_priority(car, target)
                score_other = _traffic_priority(other, other_target)
                if abs(score_car - score_other) < 1e-6 and car.route_index == other.route_index and next_wp == other_wp:
                    d_car = math.hypot(target[0] - car.x, target[1] - car.y)
                    d_other = math.hypot(other_target[0] - other.x, other_target[1] - other.y)
                    loser = car if d_car > d_other else other
                else:
                    loser = car if score_car < score_other else other
            cancelled.add(loser.vehicle_id)
            # Keep the loser in-lane while the reservation clears the winner.

    # Lateral sidesteps made touching sprites look glued together. Yielding cars
    # now remain in lane while the junction and following reservations clear the
    # winner first.

    # Phase 2b: hard safety using a spatial hash as well. This replaces the old
    # O(N^2) all-car scan, which became expensive exactly when traffic density rose.
    for _ in range(3):
        changed = False
        effective: dict[str, tuple[float, float]] = {}
        eff_grid: dict[tuple[int, int], list[TrafficVehicle]] = {}
        for car in traffic_vehicles:
            prop = proposals.get(car.vehicle_id)
            if prop is None:
                pos = (car.x, car.y)
            elif car.vehicle_id in cancelled:
                pos = (car.x, car.y)
            else:
                pos = (prop[0], prop[1])
            effective[car.vehicle_id] = pos
            eff_grid.setdefault((int(pos[0] // cell), int(pos[1] // cell)), []).append(car)
        for car in traffic_vehicles:
            if car.vehicle_id in cancelled or car.vehicle_id not in proposals:
                continue
            nx, ny = effective[car.vehicle_id]
            cx, cy = int(nx // cell), int(ny // cell)
            candidates: list[TrafficVehicle] = []
            for yy in range(cy - 1, cy + 2):
                for xx in range(cx - 1, cx + 2):
                    candidates.extend(eff_grid.get((xx, yy), ()))
            for other in candidates:
                if other is car:
                    continue
                ox, oy = effective[other.vehicle_id]
                car_heading = proposals[car.vehicle_id][2]
                other_prop = proposals.get(other.vehicle_id)
                other_heading = other_prop[2] if other_prop is not None else other.angle
                courtesy = 0.92 if car.wait_age > 3.0 and not (other.parked or other.controlled_by) else 1.0
                if _traffic_footprints_conflict(car, nx, ny, car_heading, other, ox, oy, other_heading, courtesy_scale=courtesy):
                    cancelled.add(car.vehicle_id)
                    changed = True
                    break
        if not changed:
            break

    # Phase 3: commit + wait-age/stuck recovery.
    recovery_now = time.monotonic()
    for car in traffic_vehicles:
        prop = proposals.get(car.vehicle_id)
        if prop is None:
            continue
        nx, ny, heading, speed, next_waypoint, _, red_light = prop
        car.red_light_waiting = bool(red_light and speed < 1.0)
        if car.controlled_by or car.parked or car.route_index < 0:
            continue
        moved = math.hypot(nx - car.x, ny - car.y)
        if car.vehicle_id in cancelled:
            car.speed = max(0.0, car.speed - TRAFFIC_BRAKE_DECEL * dt)
            car.wait_age = min(float(TRAFFIC_AI.get("max_wait_priority", 15.0)), car.wait_age + dt)
            car.stuck_time += dt
            if not red_light and car.stuck_time >= 0.65:
                # Ask the blocking vehicle for room before any recovery nudge.
                # A stable left/right indicator makes that intent visible to the
                # player even on a geometrically straight route segment.
                if recovery_now >= float(car.horn_until):
                    _activate_traffic_horn(car, 0.8)
                car.turn_signal = -1 if sum(ord(ch) for ch in car.vehicle_id) % 2 == 0 else 1
            recovery_after = min(
                0.9 if _traffic_junction_at(car.x, car.y) else 1.8,
                max(1.0, float(TRAFFIC_AI.get("visible_stall_recovery_seconds", 2.2))),
            )
            if not red_light and car.stuck_time >= recovery_after:
                _recover_visible_stall(car, routes[car.route_index % len(routes)])
            _try_recycle_stuck_car(car, routes, sessions)
            current_junction = _traffic_junction_at(car.x, car.y)
            prior_junction = car.junction_id
            car.junction_id = current_junction
            car.junction_time = (
                car.junction_time + dt
                if current_junction and current_junction == prior_junction
                else (dt if current_junction else 0.0)
            )
            continue
        car.x, car.y = nx, ny
        car.angle = heading
        car.speed = speed
        car.next_waypoint = next_waypoint
        current_junction = _traffic_junction_at(car.x, car.y)
        prior_junction = car.junction_id
        car.junction_id = current_junction
        car.junction_time = (
            car.junction_time + dt
            if current_junction and current_junction == prior_junction
            else (dt if current_junction else 0.0)
        )
        if moved > 0.6:
            car.wait_age = max(0.0, car.wait_age - dt * 2.4)
            car.stuck_time = max(0.0, car.stuck_time - dt * 3.0)
            car.last_progress_x, car.last_progress_y = car.x, car.y
        elif speed < 1.0 and not red_light:
            car.wait_age = min(float(TRAFFIC_AI.get("max_wait_priority", 15.0)), car.wait_age + dt * 0.5)
            car.stuck_time += dt * 0.5


clients: dict[str, ClientSession] = {}
clients_lock = asyncio.Lock()
trade_offers: dict[str, tuple[str, float]] = {}
# Development-only fallback when --memory-db is selected.
memory_accounts: dict[str, dict] = {}
memory_sms_messages: list[dict] = []
# Salted, in-memory network-source throttling. Raw addresses are never stored.
bug_report_source_times: dict[str, float] = {}


def print_machine_status() -> None:
    """Emit a small machine-readable line for the local server-control launcher."""
    housing_capacity = len(blank_house_interiors(ACTIVE_MAP))
    payload = {"players": len(clients), "max_players": MAX_PLAYERS,
               "housing_capacity": housing_capacity,
               "housing_overflow": max(0, len(clients) - housing_capacity), "map_id": ACTIVE_MAP_ID,
               "traffic_cars": sum(1 for c in traffic_vehicles if not c.parked),
               "parked_cars": sum(1 for c in traffic_vehicles if c.parked),
               "bicycles": len(bicycles), "npcs": len(npc_pedestrians),
               "server_metrics": SERVER_TICK_METRICS.public_dict()}
    print("@STATUS " + json.dumps(payload, separators=(",", ":")), flush=True)


async def send_json(ws: ServerConnection, payload: dict) -> None:
    await ws.send(json.dumps(payload, separators=(",", ":")))


async def broadcast(payload: dict) -> None:
    message = json.dumps(payload, separators=(",", ":"))
    async with clients_lock:
        recipients = [session.websocket for session in clients.values()]
    if recipients:
        await asyncio.gather(*(ws.send(message) for ws in recipients), return_exceptions=True)


def safe_name(raw: object) -> str:
    text = str(raw or "Player").strip()
    text = "".join(ch for ch in text if ch.isalnum() or ch in " _-")
    return text[:18] or "Player"


def normalize_friend_names(raw_names: object) -> set[str]:
    """Normalize a bounded client friend list without inventing default names."""
    if not isinstance(raw_names, list):
        return set()
    result: set[str] = set()
    for raw in raw_names[:200]:
        text = str(raw or "").strip()
        text = "".join(ch for ch in text if ch.isalnum() or ch in " _-")[:18].strip()
        if text:
            result.add(text.casefold())
    return result


def normalize_phone(raw: object) -> str | None:
    """Normalize formatting to a digit-only persistent key.

    This is intentionally identity-only for the prototype. It is NOT secure
    authentication; SMS/OTP or another credential should be added before a
    public deployment.
    """
    digits = re.sub(r"\D", "", str(raw or ""))
    if not 7 <= len(digits) <= 15:
        return None
    return digits


def masked_phone(phone: str) -> str:
    return "••••" + phone[-4:]


def inventory_payload(session: ClientSession) -> dict:
    return {
        "type": "inventory",
        "slots": session.inventory,
        "weight_kg": round(inventory_weight(session.inventory), 3),
        "package_count": inventory_count(session.inventory, "package"),
        "cash": session.player.cash,
    }


def initialize_hydrants() -> None:
    """Load authored fire-hydrant props into lightweight authoritative state."""
    hydrants.clear()
    for index, prop in enumerate(ACTIVE_MAP.get("street_props", []) or []):
        if str(prop.get("kind", "")) != "fire_hydrant":
            continue
        try:
            x, y = map(float, prop.get("pos", [0, 0]))
        except (TypeError, ValueError):
            continue
        hid = str(prop.get("id", f"hydrant_{index:04d}"))
        hydrants[hid] = HydrantState(hydrant_id=hid, x=x, y=y)


DOG_LEASH_LENGTH = 54.0
DOG_MAX_LEASH_LENGTH = 96.0


def _npc_on_building_footprint(x: float, y: float) -> bool:
    if GRID_WORLD is None or not hasattr(GRID_WORLD, "world_to_cell") or not hasattr(GRID_WORLD, "data"):
        return False
    gx, gy = GRID_WORLD.world_to_cell(float(x), float(y))
    for building in list((GRID_WORLD.data.get("building_synthesis") or {}).get("buildings") or []):
        try:
            x0, y0, x1, y1 = map(int, building.get("rect", ()))
        except (TypeError, ValueError):
            continue
        if x0 <= gx <= x1 and y0 <= gy <= y1:
            return True
    return False


def _recover_ambient_npc_from_rooftop(npc: NPCPedestrian) -> None:
    """Keep roof/building footprints exclusive to buyer and supplier roles."""
    if npc.kind in {"buyer", "supplier"} or not _npc_on_building_footprint(npc.x, npc.y):
        return
    routes = ACTIVE_MAP.get("npc_routes", []) or []
    if not (0 <= npc.route_index < len(routes)):
        return
    route_points = _route_points(routes[npc.route_index])
    safe_points = [
        (index, float(point[0]), float(point[1]))
        for index, point in enumerate(route_points)
        if not _npc_on_building_footprint(float(point[0]), float(point[1]))
    ]
    if not safe_points:
        return
    index, x, y = min(safe_points, key=lambda row: math.hypot(row[1] - npc.x, row[2] - npc.y))
    npc.x, npc.y = x, y
    npc.next_waypoint = (index + npc.route_direction) % len(route_points)
    npc.last_progress_x, npc.last_progress_y = x, y
    npc.pause_timer = 0.0
    npc.stuck_time = 0.0


def _dog_front_target(walker: NPCPedestrian) -> tuple[float, float]:
    """Choose a legal pavement point directly ahead of a paired walker."""
    # The dog may stand one leash-length into a registered road crossing while
    # its walker waits at the curb; traffic already yields to road occupants.
    allowed_surfaces = {"walk", "sidewalk", "road"}
    surface_fallback: tuple[float, float] | None = None
    for distance in (DOG_LEASH_LENGTH, 42.0, 30.0, 22.0, 14.0):
        for offset in (0.0, 0.55, -0.55, 1.0, -1.0):
            heading = float(walker.aim) + offset
            x = walker.x + math.cos(heading) * distance
            y = walker.y + math.sin(heading) * distance
            if GRID_WORLD is None:
                return x, y
            if GRID_WORLD.collision_at("ground", x, y) not in allowed_surfaces:
                continue
            if _npc_on_building_footprint(x, y):
                continue
            if surface_fallback is None:
                surface_fallback = (x, y)
            if hasattr(GRID_WORLD, "object_collision_at") and GRID_WORLD.object_collision_at(x, y, 7.0):
                continue
            return x, y
    # Dogs are non-colliding ambient art. If a hydrant, lamp base, or other
    # small prop occupies every ahead candidate, retain the ahead/leash contract
    # on the correct surface instead of collapsing the dog into its walker.
    return surface_fallback or (walker.x, walker.y)


def initialize_npcs() -> None:
    npc_pedestrians.clear()
    blood_stains.clear()
    npc_respawns.clear()
    routes = ACTIVE_MAP.get("npc_routes", []) or []
    starts = ACTIVE_MAP.get("npc_starts", []) or []
    if not routes or not starts:
        return
    _prepare_runtime_routes(routes, 10.0)
    for i, (start, route, route_index, x, y, next_wp, heading) in enumerate(_fixed_start_plan(routes, starts)):
        appearance = _indexed_character_appearance(int(start.get("appearance_index", i)), preset_only=False)
        npc_pedestrians.append(NPCPedestrian(
            npc_id=str(start.get("id", f"npc{i+1:03d}")), route_index=route_index, next_waypoint=next_wp,
            x=x, y=y, speed=float(route.get("speed", 54.0)) * float(start.get("speed_scale", 1.0)),
            aim=heading, appearance=appearance, pause_timer=0.0,
            last_progress_x=x, last_progress_y=y,
        ))

    # v2.5 dog walkers are paired server-authoritative companions. Each dog
    # stays ahead of one pedestrian on the same pavement route; the public pair
    # IDs let clients draw the connecting leash.
    walkers = [npc for npc in npc_pedestrians if npc.kind == "pedestrian"]
    # Reports #185/#188/#189 halve the ambient density and require a strict
    # one-walker/one-leading-dog pairing. Three distinct walkers receive one
    # companion each; no walker can be selected twice.
    dog_count = min(3, len(walkers))
    walker_stride = max(1, len(walkers) // max(1, dog_count))
    for dog_i in range(dog_count):
        if not walkers:
            break
        walker = walkers[(7 + dog_i * walker_stride) % len(walkers)]
        x, y = _dog_front_target(walker)
        if (x, y) == (walker.x, walker.y):
            continue
        dog_id = f"dog{dog_i+1:02d}"
        walker.companion_id = dog_id
        npc_pedestrians.append(NPCPedestrian(
            npc_id=dog_id, route_index=walker.route_index, next_waypoint=walker.next_waypoint,
            x=x, y=y, speed=max(42.0, walker.speed * 1.12),
            aim=walker.aim, appearance={}, pause_timer=0.0, kind="dog",
            last_progress_x=x, last_progress_y=y,
            companion_id=walker.npc_id,
        ))

    # Report #53: suppliers and buyers are real, stationary, authoritative NPCs
    # distributed across the city. They share the normal snapshot/render path
    # instead of being client-only icons painted at two legacy coordinates.
    for index, location in enumerate(ACTIVE_MAP.get("job_locations", []) or []):
        role = str(location.get("role", "")).strip().lower()
        if role not in {"supplier", "buyer"}:
            continue
        try:
            x, y = map(float, location.get("pos", [0.0, 0.0]))
        except (TypeError, ValueError):
            continue
        appearance_index = int(location.get("appearance_index", 40 + index))
        level = int(location.get("level", 1))
        npc_pedestrians.append(NPCPedestrian(
            npc_id=str(location.get("id", f"job_{role}_{index + 1:02d}")),
            route_index=-1, next_waypoint=0, x=x, y=y, speed=0.0, aim=0.0,
            appearance=_indexed_character_appearance(appearance_index, preset_only=False),
            pause_timer=0.0, kind=role, last_progress_x=x, last_progress_y=y,
            level=level,
        ))


def _npc_near_any_player(npc: NPCPedestrian, sessions: list[ClientSession], radius: float) -> bool:
    r2 = radius * radius
    return any((s.player.x - npc.x) ** 2 + (s.player.y - npc.y) ** 2 <= r2 for s in sessions)


def _nearest_sidewalk_escape(world, npc: NPCPedestrian, car: TrafficVehicle) -> tuple[float, float] | None:
    """Find the closest pavement cell that also increases car clearance."""
    gx, gy = world.world_to_cell(npc.x, npc.y)
    candidates = []
    for radius in range(1, 6):
        for y in range(gy - radius, gy + radius + 1):
            for x in range(gx - radius, gx + radius + 1):
                if not world.in_bounds(x, y):
                    continue
                cx, cy = world.cell_center(x, y)
                if world.collision_at("ground", cx, cy) not in {"walk", "sidewalk"}:
                    continue
                distance = math.hypot(cx - npc.x, cy - npc.y)
                car_clearance = math.hypot(cx - car.x, cy - car.y)
                candidates.append((distance, -car_clearance, cy, cx))
        if candidates:
            break
    if not candidates:
        return None
    _distance, _clearance, cy, cx = min(candidates)
    return float(cx), float(cy)


def _pedestrian_signal_allows_entry(world, x: float, y: float, nx: float, ny: float, server_time: float) -> bool:
    """Hold pedestrians at the curb while conflicting vehicle traffic is green."""
    if world is None or world.collision_at("ground", x, y) == "road":
        return True
    if world.collision_at("ground", nx, ny) != "road":
        return True
    next_cell = world.world_to_cell(nx, ny)
    for crossing in getattr(world, "_v110_crosswalks", ()):
        if next_cell not in crossing.road_cells():
            continue
        conflicting_vehicle_phase = 1 if crossing.axis == "x" else 0
        return not traffic_phase_green(conflicting_vehicle_phase, server_time)
    return False


def _pedestrian_vehicle_allows_entry(world, x: float, y: float, nx: float, ny: float) -> bool:
    """Let pedestrians choose crossings, but hold at the curb for nearby cars."""
    if world is None or world.collision_at("ground", x, y) == "road":
        return True
    if world.collision_at("ground", nx, ny) != "road":
        return True
    for car in traffic_vehicles:
        dx, dy = nx - car.x, ny - car.y
        distance = math.hypot(dx, dy)
        close_radius = car.collision_length * 0.5 + 58.0
        if distance <= close_radius:
            return False
        if abs(car.speed) < 4.0:
            continue
        direction = 1.0 if car.speed >= 0.0 else -1.0
        hx = math.cos(car.angle) * direction
        hy = math.sin(car.angle) * direction
        forward = dx * hx + dy * hy
        lateral = abs(-dx * hy + dy * hx)
        approach = max(190.0, abs(car.speed) * 0.9 + car.collision_length * 0.5)
        if -car.collision_length * 0.35 < forward < approach and lateral < car.collision_width * 0.5 + 38.0:
            return False
    return True


def _resolve_npc_personal_space(world, personal_space: float) -> int:
    """Apply soft pedestrian body separation while preserving legal surfaces."""
    if world is None:
        return 0
    movers = [npc for npc in npc_pedestrians if npc.kind == "pedestrian" and npc.route_index >= 0]
    minimum = max(20.0, float(personal_space) * 0.90)
    resolved = 0
    for _pass in range(2):
        grid = build_spatial_grid(movers, max(64.0, minimum * 2.5))
        checked: set[tuple[str, str]] = set()
        for npc in sorted(movers, key=lambda item: item.npc_id):
            for other in nearby_from_grid(npc, grid, max(64.0, minimum * 2.5), 1):
                if other is npc:
                    continue
                pair = tuple(sorted((npc.npc_id, other.npc_id)))
                if pair in checked:
                    continue
                checked.add(pair)
                dx, dy = other.x - npc.x, other.y - npc.y
                distance = math.hypot(dx, dy)
                if distance >= minimum:
                    continue
                if distance < 0.01:
                    angle = math.radians(sum(ord(ch) for ch in pair[0]) % 360)
                    ux, uy = math.cos(angle), math.sin(angle)
                else:
                    ux, uy = dx / distance, dy / distance
                separation = (minimum - distance) * 0.5 + 0.6
                candidates = (
                    (npc.x - ux * separation, npc.y - uy * separation,
                     other.x + ux * separation, other.y + uy * separation),
                    (npc.x - uy * separation, npc.y + ux * separation,
                     other.x + uy * separation, other.y - ux * separation),
                )
                current_a = world.collision_at("ground", npc.x, npc.y)
                current_b = world.collision_at("ground", other.x, other.y)
                for ax, ay, bx, by in candidates:
                    surface_a = world.collision_at("ground", ax, ay)
                    surface_b = world.collision_at("ground", bx, by)
                    allowed_a = {"road"} if current_a == "road" else {"walk", "sidewalk"}
                    allowed_b = {"road"} if current_b == "road" else {"walk", "sidewalk"}
                    if surface_a not in allowed_a or surface_b not in allowed_b:
                        continue
                    if world.object_collision_at(ax, ay, 7.0) or world.object_collision_at(bx, by, 7.0):
                        continue
                    npc.x, npc.y = ax, ay
                    other.x, other.y = bx, by
                    resolved += 1
                    break
    return resolved


def _update_dog_walkers(dt: float) -> None:
    """Keep each dog visibly ahead of its walker with a bounded leash."""
    by_id = {npc.npc_id: npc for npc in npc_pedestrians}
    for dog in (npc for npc in npc_pedestrians if npc.kind == "dog"):
        walker = by_id.get(dog.companion_id)
        if walker is None or walker.kind != "pedestrian":
            continue
        target_x, target_y = _dog_front_target(walker)
        dog.x, dog.y = target_x, target_y
        dog.aim = walker.aim
        dog.route_index = walker.route_index
        dog.next_waypoint = walker.next_waypoint
        dog.route_direction = walker.route_direction
        dog.pause_timer = walker.pause_timer
        dog.last_progress_x, dog.last_progress_y = dog.x, dog.y


def update_npcs(
    dt: float,
    sessions: list[ClientSession],
    tick_index: int,
    server_time: float | None = None,
) -> None:
    routes = ACTIVE_MAP.get("npc_routes", []) or []
    if not routes or not npc_pedestrians:
        return

    personal_space = float(NPC_AI.get("personal_space_px", 26.0))
    active_radius = float(NPC_AI.get("active_radius_px", 1800.0))
    far_hz = max(1.0, float(NPC_AI.get("far_update_hz", 5.0)))
    far_stride = max(1, int(round(AMBIENT_SIM_RATE / far_hz)))
    job_npcs = [npc for npc in npc_pedestrians if npc.kind in {"supplier", "buyer"}]
    moving_npcs = [npc for npc in npc_pedestrians if 0 <= npc.route_index < len(routes)]
    # Stationary job NPCs have their own keep-clear rule below and must not be
    # treated as members of the ambient crowd spatial hash.
    grid = build_spatial_grid(moving_npcs, max(64.0, personal_space * 3.0))

    signal_time = time.time() if server_time is None else float(server_time)
    for npc in npc_pedestrians:
        npc.signal_waiting = False
        _recover_ambient_npc_from_rooftop(npc)
        if npc.kind == "dog":
            continue
        near_player = _npc_near_any_player(npc, sessions, active_radius)
        if not near_player and tick_index % far_stride != (sum(ord(c) for c in npc.npc_id) % far_stride):
            # Distant pedestrians sleep most ticks. Scale the occasional step so
            # their average route speed remains approximately unchanged.
            continue
        step_dt = dt if near_player else dt * far_stride

        if npc.pause_timer > 0.0:
            npc.pause_timer = max(0.0, npc.pause_timer - step_dt)
            continue
        if not (0 <= npc.route_index < len(routes)):
            continue
        route = routes[npc.route_index]
        points = _route_points(route)
        if len(points) < 2:
            continue
        tx, ty = points[npc.next_waypoint % len(points)]
        dx, dy = float(tx) - npc.x, float(ty) - npc.y
        dist = math.hypot(dx, dy)
        if dist < 1e-6:
            npc.next_waypoint = (npc.next_waypoint + npc.route_direction) % len(points)
            continue
        ux, uy = dx / dist, dy / dist

        # Report #58: ambient pedestrians are non-blocking to one another at
        # route level, so they never form permanent single-file walls. Report
        # #159 adds legal sidesteps and soft separation for visible bodies.
        current_surface = GRID_WORLD.collision_at("ground", npc.x, npc.y) if GRID_WORLD is not None else "sidewalk"
        job_clearance = max(92.0, personal_space * 3.4)
        nearest_job = min(
            (
                (math.hypot(npc.x - role_npc.x, npc.y - role_npc.y), role_npc)
                for role_npc in job_npcs
                if role_npc is not npc
            ),
            default=(float("inf"), None),
            key=lambda row: row[0],
        )
        if nearest_job[1] is not None and nearest_job[0] < job_clearance and current_surface != "road":
            role_npc = nearest_job[1]
            away_x, away_y = npc.x - role_npc.x, npc.y - role_npc.y
            if nearest_job[0] < 1.0:
                identity_angle = math.radians(sum(ord(ch) for ch in npc.npc_id) % 360)
                away_x, away_y = math.cos(identity_angle), math.sin(identity_angle)
            away_mag = max(1.0, math.hypot(away_x, away_y))
            away_x, away_y = away_x / away_mag, away_y / away_mag
            escape_step = min(
                job_clearance - nearest_job[0] + personal_space,
                max(18.0, npc.speed * step_dt * 2.2),
            )
            candidates = []
            for turn in (0.0, 0.55, -0.55, 1.05, -1.05):
                ca, sa = math.cos(turn), math.sin(turn)
                vx, vy = away_x * ca - away_y * sa, away_x * sa + away_y * ca
                nx, ny = npc.x + vx * escape_step, npc.y + vy * escape_step
                surface = GRID_WORLD.collision_at("ground", nx, ny) if GRID_WORLD is not None else "sidewalk"
                if surface not in {"walk", "sidewalk"}:
                    continue
                clearance = min(
                    (math.hypot(nx - other.x, ny - other.y) for other in job_npcs),
                    default=job_clearance,
                )
                candidates.append((clearance, nx, ny, math.atan2(vy, vx)))
            if candidates:
                _clearance, npc.x, npc.y, npc.aim = max(candidates, key=lambda row: row[0])
                npc.pause_timer = 0.0
                npc.stuck_time += step_dt
                # Rejoin beyond the job rather than walking straight back into
                # the same buyer/supplier on the following tick.
                for offset in range(1, min(5, len(points)) + 1):
                    candidate_wp = (npc.next_waypoint + npc.route_direction * offset) % len(points)
                    wx, wy = points[candidate_wp]
                    if math.hypot(float(wx) - role_npc.x, float(wy) - role_npc.y) >= job_clearance:
                        npc.next_waypoint = candidate_wp
                        break
                if math.hypot(npc.x - npc.last_progress_x, npc.y - npc.last_progress_y) >= personal_space:
                    npc.last_progress_x, npc.last_progress_y = npc.x, npc.y
                    npc.stuck_time = 0.0
                continue
        road_hazard = None
        road_hazard_distance = 240.0
        if current_surface == "road":
            for car in traffic_vehicles:
                distance = math.hypot(npc.x - car.x, npc.y - car.y)
                if distance < road_hazard_distance:
                    road_hazard, road_hazard_distance = car, distance
        if road_hazard is not None and GRID_WORLD is not None:
            escape = _nearest_sidewalk_escape(GRID_WORLD, npc, road_hazard)
            if escape is not None:
                ex, ey = escape
                escape_dx, escape_dy = ex - npc.x, ey - npc.y
                escape_dist = max(1.0, math.hypot(escape_dx, escape_dy))
                run_step = min(escape_dist, max(24.0, npc.speed * step_dt * 3.2))
                nx = npc.x + escape_dx / escape_dist * run_step
                ny = npc.y + escape_dy / escape_dist * run_step
                if GRID_WORLD.collision_at("ground", nx, ny) in {"road", "walk", "sidewalk"}:
                    npc.x, npc.y = nx, ny
                    npc.aim = math.atan2(escape_dy, escape_dx)
                    npc.pause_timer = 0.0
                    npc.stuck_time = max(npc.stuck_time, 0.5)
                    npc.last_progress_x, npc.last_progress_y = nx, ny
                    continue
        horn_car = None
        horn_distance = 220.0 if npc.kind == "pedestrian" else 150.0
        for car in traffic_vehicles:
            if time.monotonic() >= float(car.horn_until):
                continue
            distance = math.hypot(npc.x - car.x, npc.y - car.y)
            if distance <= horn_distance and (horn_car is None or distance < horn_distance):
                horn_car = car
                horn_distance = distance

        neighbours = nearby_from_grid(npc, grid, max(64.0, personal_space * 3.0), 1)
        crowded = any(
            other is not npc
            and (other.x - npc.x) ** 2 + (other.y - npc.y) ** 2 < personal_space ** 2
            for other in neighbours
        )
        # Pedestrians already on a crossing are non-blocking; keep following
        # the authored crossing route instead of trying a sidewalk-only crowd
        # sidestep and flipping direction forever in the road.
        if horn_car is not None or (crowded and current_surface != "road"):
            identity = sum(ord(c) for c in npc.npc_id)
            sx, sy = -uy, ux
            npc.stuck_time += step_dt
            fleeing_horn = horn_car is not None
            moved_aside = False
            if fleeing_horn:
                away_x, away_y = npc.x - horn_car.x, npc.y - horn_car.y
                away_mag = max(1.0, math.hypot(away_x, away_y))
                forward_x, forward_y = away_x / away_mag, away_y / away_mag
            else:
                forward_x, forward_y = ux, uy
            directions = ((1.0, -1.0) if identity % 2 == 0 else (-1.0, 1.0))
            fallback_candidate = None
            fallback_clearance = -1.0
            for direction in (*directions, 0.0):
                escape_step = min(personal_space * (1.35 if fleeing_horn else 1.0), max(10.0, npc.speed * step_dt * 1.5))
                lateral_step = personal_space * (1.45 if npc.stuck_time >= 0.7 else 1.15) * direction
                nx = npc.x + forward_x * escape_step + sx * lateral_step
                ny = npc.y + forward_y * escape_step + sy * lateral_step
                surface = GRID_WORLD.collision_at("ground", nx, ny) if GRID_WORLD is not None else "sidewalk"
                # Escape steering stays on pavement. Authored route movement is
                # the sole authority for road entry and already uses registered
                # zebra corridors, so a sidestep cannot strand an NPC in a lane.
                allowed = {"walk", "sidewalk"}
                if surface not in allowed:
                    continue
                clearance = min(
                    (math.hypot(other.x - nx, other.y - ny) for other in neighbours if other is not npc),
                    default=personal_space * 2.0,
                )
                if clearance > fallback_clearance:
                    fallback_candidate = (nx, ny, math.atan2(forward_y, forward_x))
                    fallback_clearance = clearance
                if clearance < personal_space:
                    continue
                npc.x, npc.y, npc.aim = nx, ny, math.atan2(forward_y, forward_x)
                moved_aside = True
                break
            if not moved_aside and fallback_candidate is not None:
                # Pedestrians are intentionally non-blocking. In a completely
                # packed cluster, take the safest legal candidate instead of
                # oscillating route direction forever behind nearby bodies.
                npc.x, npc.y, npc.aim = fallback_candidate
                moved_aside = True
            if npc.stuck_time >= 1.10:
                # Corner/crowd watchdog: keep the authored route direction and
                # skip the contested point instead of alternating forever.
                npc.next_waypoint = (npc.next_waypoint + npc.route_direction) % len(points)
                npc.stuck_time = 0.0
                npc.last_progress_x, npc.last_progress_y = npc.x, npc.y
            if not moved_aside:
                npc.pause_timer = 0.0
            continue

        # Five-cell avenues are much wider than the legacy pedestrian scale.
        # Cross at a brisk clearance pace so a walker admitted during the
        # pedestrian phase leaves the conflict box before vehicles regain green.
        crossing_multiplier = 3.0 if current_surface == "road" else 1.0
        step = min(dist, npc.speed * step_dt * crossing_multiplier)
        nx, ny = npc.x + ux * step, npc.y + uy * step
        if (GRID_WORLD is not None and hasattr(GRID_WORLD, "object_collision_at")
                and GRID_WORLD.object_collision_at(nx, ny, 8.0)):
            # Never let a pavement route hidden beneath a building footprint
            # pull a crowd through its roof. Skip the obstructed waypoint and
            # stay on the last legal visible pavement point.
            npc.next_waypoint = (npc.next_waypoint + npc.route_direction) % len(points)
            npc.pause_timer = 0.0
            npc.stuck_time = 0.0
            continue
        if (not _pedestrian_signal_allows_entry(GRID_WORLD, npc.x, npc.y, nx, ny, signal_time)
                or not _pedestrian_vehicle_allows_entry(GRID_WORLD, npc.x, npc.y, nx, ny)):
            npc.signal_waiting = True
            npc.pause_timer = 0.0
            npc.aim = math.atan2(uy, ux)
            continue
        npc.x, npc.y = nx, ny
        npc.aim = math.atan2(uy, ux)
        if math.hypot(npc.x - npc.last_progress_x, npc.y - npc.last_progress_y) >= personal_space * 0.5:
            npc.last_progress_x, npc.last_progress_y = npc.x, npc.y
            npc.stuck_time = 0.0
        else:
            npc.stuck_time += step_dt
            if npc.stuck_time >= 1.25:
                npc.next_waypoint = (npc.next_waypoint + npc.route_direction) % len(points)
                npc.stuck_time = 0.0
                npc.last_progress_x, npc.last_progress_y = npc.x, npc.y
        if dist <= max(6.0, npc.speed * step_dt * 1.25):
            npc.next_waypoint = (npc.next_waypoint + npc.route_direction) % len(points)
            npc.step_counter += 1
            # A small deterministic subset occasionally changes its mind at a
            # waypoint. Personal-space yielding keeps the reversal collision-safe.
            identity = sum(ord(c) for c in npc.npc_id)
            if npc.kind == "pedestrian" and identity % 27 == 0 and (identity + npc.step_counter) % 31 == 0:
                npc.route_direction *= -1
                npc.next_waypoint = (npc.next_waypoint + npc.route_direction * 2) % len(points)
                npc.pause_timer = 0.35
            # Fixed cadence: no probability rolls. Most waypoints are continuous;
            # every 12th completed segment gets a brief deterministic pause.
            if (sum(ord(c) for c in npc.npc_id) + npc.step_counter) % 12 == 0:
                npc.pause_timer = 0.25

    _resolve_npc_personal_space(GRID_WORLD, personal_space)
    _update_dog_walkers(dt)


def vehicle_speed_mph(speed_px_s: float) -> float:
    return abs(float(speed_px_s)) * max(0.01, float(VEHICLE_SETTINGS.get("mph_per_px_s", 0.18)))


def player_signal_turn_multiplier(car: TrafficVehicle, steer: float) -> float:
    """Reward a driver for indicating in the direction they are steering."""
    steer_direction = -1 if float(steer) < -0.02 else (1 if float(steer) > 0.02 else 0)
    if steer_direction and int(car.turn_signal) == steer_direction:
        return max(1.0, float(VEHICLE_SETTINGS.get("player_signal_turn_multiplier", 1.32)))
    return 1.0


def _apply_player_handbrake(car: TrafficVehicle, dt: float) -> None:
    deceleration = float(VEHICLE_SETTINGS.get("player_handbrake_px_s2", 760.0))
    car.brake_lights = True
    if car.speed > 0.0:
        car.speed = max(0.0, car.speed - deceleration * max(0.0, float(dt)))
    elif car.speed < 0.0:
        car.speed = min(0.0, car.speed + deceleration * max(0.0, float(dt)))


def _point_clear_of_vehicles(x: float, y: float, radius: float, ignored: TrafficVehicle) -> bool:
    for other in traffic_vehicles:
        if other is ignored:
            continue
        dx, dy = x - other.x, y - other.y
        ca, sa = math.cos(other.angle), math.sin(other.angle)
        longitudinal = abs(dx * ca + dy * sa)
        lateral = abs(-dx * sa + dy * ca)
        if (longitudinal < other.collision_length * 0.5 + radius
                and lateral < other.collision_width * 0.5 + radius):
            return False
    return True


def _displace_point_from_car(
    x: float, y: float, radius: float, car: TrafficVehicle,
) -> tuple[float, float] | None:
    """Return a nearby legal pose outside a car body, or None if not overlapping."""
    dx, dy = float(x) - car.x, float(y) - car.y
    ca, sa = math.cos(car.angle), math.sin(car.angle)
    longitudinal = dx * ca + dy * sa
    lateral = -dx * sa + dy * ca
    half_l = car.collision_length * 0.5
    half_w = car.collision_width * 0.5
    if abs(longitudinal) >= half_l + radius or abs(lateral) >= half_w + radius:
        return None
    identity = sum(ord(ch) for ch in car.vehicle_id)
    lateral_sign = 1.0 if lateral > 0.5 else (-1.0 if lateral < -0.5 else (1.0 if identity % 2 else -1.0))
    longitudinal_sign = 1.0 if longitudinal > 0.5 else (-1.0 if longitudinal < -0.5 else (1.0 if car.speed >= 0.0 else -1.0))
    clearance = 8.0
    local_candidates = (
        (max(-half_l, min(half_l, longitudinal)), lateral_sign * (half_w + radius + clearance)),
        (max(-half_l, min(half_l, longitudinal)), -lateral_sign * (half_w + radius + clearance)),
        (longitudinal_sign * (half_l + radius + clearance), lateral),
        (-longitudinal_sign * (half_l + radius + clearance), lateral),
    )
    for local_x, local_y in local_candidates:
        nx = car.x + ca * local_x - sa * local_y
        ny = car.y + sa * local_x + ca * local_y
        if GRID_RUNTIME_ACTIVE and GRID_WORLD is not None:
            if not GRID_WORLD.circle_walkable("ground", nx, ny, radius):
                continue
        elif blocked(nx, ny, ACTIVE_MAP, level=0):
            continue
        if _point_clear_of_vehicles(nx, ny, radius, car):
            return nx, ny
    return None


def update_player_vehicle_impacts(sessions: list[ClientSession], now: float) -> None:
    """Displace struck players and put them prone instead of leaving an overlap."""
    moving_cars = [
        car for car in traffic_vehicles
        if not car.parked and vehicle_speed_mph(car.speed) >= 12.0
    ]
    for session in sessions:
        if (session.driving_vehicle_id or session.passenger_vehicle_id or session.riding_bicycle_id
                or session.player.interior_id or int(session.player.level) != 0):
            continue
        if now < float(session.collision_disabled_until):
            continue
        for car in moving_cars:
            dx, dy = session.player.x - car.x, session.player.y - car.y
            ca, sa = math.cos(car.angle), math.sin(car.angle)
            longitudinal = abs(dx * ca + dy * sa)
            lateral = abs(-dx * sa + dy * ca)
            if (longitudinal > car.collision_length * 0.5 + PLAYER_RADIUS * 0.55
                    or lateral > car.collision_width * 0.5 + PLAYER_RADIUS * 0.55):
                continue
            displaced = _displace_point_from_car(session.player.x, session.player.y, PLAYER_RADIUS, car)
            if displaced is not None:
                session.player.x, session.player.y = displaced
            session.prone = True
            session.crouching = False
            session.crouch_cancel_latched = bool(session.crouch_requested)
            session.stand_delay_remaining = 0.0
            session.jump_kind = ""
            session.jump_until = 0.0
            session.jump_velocity_x = 0.0
            session.jump_velocity_y = 0.0
            session.boost = False
            session.forced_prone_until = now + 1.10
            session.collision_disabled_until = now + 1.45
            break


def displace_low_speed_npcs() -> int:
    """Shove ambient NPCs clear below run-over speed instead of pinning traffic."""
    runover_mph = max(1.0, float(NPC_AI.get("runover_min_speed_mph", 30.0)))
    moving_cars = [
        car for car in traffic_vehicles
        if not car.parked and 0.8 <= vehicle_speed_mph(car.speed) < runover_mph
    ]
    displaced_count = 0
    for npc in npc_pedestrians:
        if npc.kind in {"supplier", "buyer", "dog"}:
            continue
        for car in moving_cars:
            displaced = _displace_point_from_car(npc.x, npc.y, 9.0, car)
            if displaced is None:
                continue
            npc.x, npc.y = displaced
            npc.last_progress_x, npc.last_progress_y = displaced
            npc.stuck_time = 0.0
            npc.pause_timer = 0.0
            displaced_count += 1
            break
    return displaced_count


def update_hydrants(now: float) -> None:
    """Break authored hydrants on >30 mph car impacts and respawn after five minutes."""
    if not hydrants:
        return
    for hydrant in hydrants.values():
        if hydrant.broken_until > 0.0 and now >= hydrant.broken_until:
            hydrant.broken_until = 0.0
            hydrant.water_until = 0.0
        if hydrant.broken_until > now:
            continue
        for car in traffic_vehicles:
            if vehicle_speed_mph(car.speed) <= HYDRANT_BREAK_MPH:
                continue
            direction = 1.0 if car.speed >= 0.0 else -1.0
            nose_x = car.x + math.cos(car.angle) * car.collision_length * 0.46 * direction
            nose_y = car.y + math.sin(car.angle) * car.collision_length * 0.46 * direction
            hit_radius = HYDRANT_HIT_RADIUS + car.collision_width * 0.38
            if (nose_x - hydrant.x) ** 2 + (nose_y - hydrant.y) ** 2 > hit_radius ** 2:
                continue
            hydrant.broken_until = now + HYDRANT_RESPAWN_SECONDS
            hydrant.water_until = now + HYDRANT_WATER_SECONDS
            car.speed *= 0.86
            break


def update_npc_runovers(now: float) -> None:
    """Replace pedestrians struck by a moving vehicle after a short delay."""
    blood_stains[:] = [stain for stain in blood_stains if stain.expires_at > now]
    routes = ACTIVE_MAP.get("npc_routes", []) or []
    for pending in list(npc_respawns):
        if pending.due_at > now or not (0 <= pending.route_index < len(routes)):
            continue
        points = _route_points(routes[pending.route_index])
        if not points:
            npc_respawns.remove(pending)
            continue
        spawn_index = (pending.next_waypoint + 2) % len(points)
        x, y = map(float, points[spawn_index])
        next_index = (spawn_index + 1) % len(points)
        tx, ty = map(float, points[next_index])
        npc_pedestrians.append(NPCPedestrian(
            npc_id=f"respawn{uuid.uuid4().hex[:8]}",
            route_index=pending.route_index,
            next_waypoint=next_index,
            x=x, y=y, speed=pending.speed,
            aim=math.atan2(ty - y, tx - x),
            appearance=normalize_character(pending.appearance),
            pause_timer=0.2,
        ))
        npc_respawns.remove(pending)

    min_speed_mph = max(1.0, float(NPC_AI.get("runover_min_speed_mph", 30.0)))
    stain_seconds = max(1.0, float(NPC_AI.get("blood_stain_seconds", 12.0)))
    respawn_seconds = max(1.0, float(NPC_AI.get("runover_respawn_seconds", 18.0)))
    moving_cars = [car for car in traffic_vehicles if vehicle_speed_mph(car.speed) >= min_speed_mph]
    victims: list[NPCPedestrian] = []
    for npc in npc_pedestrians:
        if npc.kind in {"supplier", "buyer", "dog"}:
            continue
        for car in moving_cars:
            dx, dy = npc.x - car.x, npc.y - car.y
            ca, sa = math.cos(car.angle), math.sin(car.angle)
            longitudinal = abs(dx * ca + dy * sa)
            lateral = abs(-dx * sa + dy * ca)
            if longitudinal <= car.collision_length * 0.5 + 7.0 and lateral <= car.collision_width * 0.5 + 7.0:
                victims.append(npc)
                break
    for npc in victims:
        if npc not in npc_pedestrians:
            continue
        npc_pedestrians.remove(npc)
        blood_stains.append(BloodStain(
            stain_id=f"blood{uuid.uuid4().hex[:8]}", x=npc.x, y=npc.y,
            expires_at=now + stain_seconds,
        ))
        npc_respawns.append(NPCRespawn(
            due_at=now + respawn_seconds,
            route_index=npc.route_index,
            next_waypoint=npc.next_waypoint,
            speed=npc.speed,
            appearance=normalize_character(npc.appearance),
        ))


def nearest_vehicle(x: float, y: float, radius: float = 86.0) -> TrafficVehicle | None:
    best = None
    best_d = float(radius)
    for car in traffic_vehicles:
        d = math.hypot(car.x - x, car.y - y)
        if d <= best_d:
            best = car
            best_d = d
    return best


def _vehicle_map_blocked(car: TrafficVehicle, x: float, y: float, angle: float) -> bool:
    """Test the complete rotated car body against world, water and buildings."""
    hl = max(12.0, car.collision_length * 0.5)
    hw = max(8.0, car.collision_width * 0.5)
    ca, sa = math.cos(angle), math.sin(angle)
    extent_x = abs(ca) * hl + abs(sa) * hw
    extent_y = abs(sa) * hl + abs(ca) * hw
    world_w = float(ACTIVE_MAP.get("world_w", 0.0))
    world_h = float(ACTIVE_MAP.get("world_h", 0.0))
    if x - extent_x <= 0.0 or y - extent_y <= 0.0 or x + extent_x >= world_w or y + extent_y >= world_h:
        return True
    samples = [
        (x, y),
        (x + ca * hl, y + sa * hl), (x - ca * hl, y - sa * hl),
        (x - sa * hw, y + ca * hw), (x + sa * hw, y - ca * hw),
        (x + ca * hl - sa * hw, y + sa * hl + ca * hw),
        (x + ca * hl + sa * hw, y + sa * hl - ca * hw),
        (x - ca * hl - sa * hw, y - sa * hl + ca * hw),
        (x - ca * hl + sa * hw, y - sa * hl - ca * hw),
    ]
    for px, py in samples:
        if point_in_water(px, py, ACTIVE_MAP) and not point_near_road(
            px, py, ACTIVE_MAP, extra=0.0, bridge_only=True, level=0
        ):
            return True
        if GRID_RUNTIME_ACTIVE and GRID_WORLD is not None and GRID_WORLD.object_collision_at(px, py, 4.0):
            return True
    rects = collision_buildings_near(x, y, ACTIVE_MAP) if ACTIVE_MAP.get("chunked") else ACTIVE_MAP.get("buildings", [])
    for rx, ry, rw, rh in rects:
        if _oriented_boxes_overlap(
            x, y, angle, hl * 2.0, hw * 2.0,
            float(rx) + float(rw) * 0.5, float(ry) + float(rh) * 0.5,
            0.0, float(rw), float(rh),
        ):
            return True
    return False


def _vehicle_hits_vehicle(car: TrafficVehicle, x: float, y: float, angle: float) -> bool:
    for other in traffic_vehicles:
        if other is car:
            continue
        if _oriented_boxes_overlap(
            x, y, angle, car.collision_length, car.collision_width,
            other.x, other.y, other.angle, other.collision_length, other.collision_width,
        ):
            return True
    return False


def _push_blocking_vehicles(car: TrafficVehicle, x: float, y: float, angle: float, push_step: float) -> bool:
    """Move non-player cars clear of a player car's proposed footprint."""
    blockers = [
        other for other in traffic_vehicles
        if other is not car and _oriented_boxes_overlap(
            x, y, angle, car.collision_length, car.collision_width,
            other.x, other.y, other.angle, other.collision_length, other.collision_width,
        )
    ]
    if not blockers:
        return True
    # Never relocate another player's authoritative car behind their back.
    if any(other.controlled_by for other in blockers):
        return False
    direction = 1.0 if car.speed >= 0.0 else -1.0
    forward = (math.cos(angle) * direction, math.sin(angle) * direction)
    for other in blockers:
        radial_x, radial_y = other.x - x, other.y - y
        radial_mag = math.hypot(radial_x, radial_y)
        radial = forward if radial_mag < 1.0 else (radial_x / radial_mag, radial_y / radial_mag)
        side = (-forward[1], forward[0])
        moved = False
        for ux, uy in (radial, forward, side, (-side[0], -side[1])):
            for factor in (1.0, 1.55, 2.1, 3.2, 4.6):
                distance = max(10.0, float(push_step)) * factor
                ox, oy = other.x + ux * distance, other.y + uy * distance
                if _vehicle_map_blocked(other, ox, oy, other.angle):
                    continue
                if _oriented_boxes_overlap(
                    x, y, angle, car.collision_length, car.collision_width,
                    ox, oy, other.angle, other.collision_length, other.collision_width,
                ):
                    continue
                occupied = any(
                    third is not car and third is not other and _oriented_boxes_overlap(
                        ox, oy, other.angle, other.collision_length, other.collision_width,
                        third.x, third.y, third.angle, third.collision_length, third.collision_width,
                    )
                    for third in traffic_vehicles
                )
                if occupied:
                    continue
                other.x, other.y = ox, oy
                other.last_progress_x, other.last_progress_y = ox, oy
                other.speed = max(other.speed, abs(car.speed) * 0.28)
                other.stuck_time = 0.0
                moved = True
                break
            if moved:
                break
        if not moved:
            return False
    return not _vehicle_hits_vehicle(car, x, y, angle)


def _spawn_ejected_driver(car: TrafficVehicle) -> None:
    routes = ACTIVE_MAP.get("npc_routes", []) or []
    if not routes:
        return
    # Attach the ejected driver to the closest sidewalk route, so after a theft
    # they visibly leave the road instead of disappearing.
    best_route = 0
    best_wp = 0
    best_d = float("inf")
    for ri, route in enumerate(routes):
        for wi, pt in enumerate(route.get("waypoints", []) or []):
            d = (float(pt[0]) - car.x) ** 2 + (float(pt[1]) - car.y) ** 2
            if d < best_d:
                best_d, best_route, best_wp = d, ri, wi
    appearance_index = sum(ord(ch) for ch in car.vehicle_id)
    side_x = car.x + math.cos(car.angle + math.pi / 2.0) * 32.0
    side_y = car.y + math.sin(car.angle + math.pi / 2.0) * 32.0
    appearance = _indexed_character_appearance(appearance_index, preset_only=False)
    npc_pedestrians.append(NPCPedestrian(
        npc_id=f"driver{uuid.uuid4().hex[:6]}", route_index=best_route,
        next_waypoint=best_wp, x=side_x, y=side_y, speed=62.0,
        aim=car.angle + math.pi / 2.0, appearance=appearance, pause_timer=0.15,
    ))


def _spawn_dismounted_cyclist(bike: BicycleState) -> None:
    routes = ACTIVE_MAP.get("npc_routes", []) or []
    if not routes:
        return
    best_route, best_wp, best_d = 0, 0, float("inf")
    for ri, route in enumerate(routes):
        for wi, pt in enumerate(route.get("waypoints", []) or []):
            d = (float(pt[0]) - bike.x) ** 2 + (float(pt[1]) - bike.y) ** 2
            if d < best_d:
                best_d, best_route, best_wp = d, ri, wi
    npc_pedestrians.append(NPCPedestrian(
        npc_id=f"cyclist{uuid.uuid4().hex[:6]}", route_index=best_route, next_waypoint=best_wp,
        x=bike.x + math.cos(bike.angle + math.pi/2) * 24.0,
        y=bike.y + math.sin(bike.angle + math.pi/2) * 24.0,
        speed=58.0, aim=bike.angle + math.pi/2,
        appearance=normalize_character(bike.appearance), pause_timer=0.25,
    ))


def _interior_info(interior_id: str) -> dict | None:
    wanted = str(interior_id).strip()
    return next((row for row in ACTIVE_MAP.get("interiors", []) or [] if str(row.get("id", "")) == wanted), None)


def _near_apartment_buzzer(viewer: ClientSession, interior_id: str) -> bool:
    """Return whether an outdoor player is close enough to read a buzzer."""
    if viewer.player.interior_id:
        return False
    info = _interior_info(interior_id)
    if info is None:
        return False
    try:
        ex, ey = float(info["entry"][0]), float(info["entry"][1])
    except (KeyError, TypeError, ValueError, IndexError):
        return False
    return math.hypot(viewer.player.x - ex, viewer.player.y - ey) <= APARTMENT_BUZZER_VISIBILITY_DISTANCE


def _can_view_apartment_residency(viewer: ClientSession, resident: ClientSession) -> bool:
    """Enforce self/friend/buzzer visibility for apartment residency."""
    if viewer is resident:
        return True
    mutual_friends = (
        resident.player.name.casefold() in viewer.friend_names
        and viewer.player.name.casefold() in resident.friend_names
    )
    if mutual_friends:
        return True
    return _near_apartment_buzzer(viewer, resident.apartment_interior_id)


def _interior_state_payload(player: PlayerState) -> dict:
    info = _interior_info(player.interior_id) if player.interior_id else None
    return {
        "type": "interior_state",
        "active": bool(player.interior_id),
        "interior_id": player.interior_id,
        "name": str(info.get("name", "Interior")) if info else "",
        "x": int(player.interior_x),
        "y": int(player.interior_y),
        "aim": round(float(player.interior_aim), 4),
    }


async def process_interior_action(session: ClientSession, action: str, message: dict) -> None:
    """Authoritative room identity and tile movement for shared interiors."""
    player = session.player
    if action == "enter":
        if player.in_vehicle:
            await send_json(session.websocket, {"type": "notice", "text": "Exit the vehicle before entering a building."})
            return
        info = _interior_info(str(message.get("interior_id", "")))
        if info is None:
            await send_json(session.websocket, {"type": "notice", "text": "That interior is unavailable."})
            return
        try:
            ex, ey = float(info["entry"][0]), float(info["entry"][1])
        except (KeyError, TypeError, ValueError, IndexError):
            return
        if math.hypot(player.x - ex, player.y - ey) > 120.0:
            await send_json(session.websocket, {"type": "notice", "text": "Move closer to the entrance."})
            return
        player.interior_id = str(info.get("id", ""))
        player.interior_x, player.interior_y = INTERIOR_START_TILE
        player.interior_aim = -math.pi / 2.0
        session.input_x = session.input_y = 0.0
        session.boost = False
        reset_on_foot_actions(session)
        await send_json(session.websocket, _interior_state_payload(player))
        return

    if action == "move":
        if not player.interior_id:
            return
        try:
            dx, dy = int(message.get("dx", 0)), int(message.get("dy", 0))
        except (TypeError, ValueError):
            return
        nx, ny, aim = interior_step(
            player.interior_id, player.interior_x, player.interior_y, dx, dy
        )
        player.interior_x, player.interior_y, player.interior_aim = nx, ny, aim
        await send_json(session.websocket, _interior_state_payload(player))
        return

    if action == "exit" and player.interior_id:
        player.interior_id = ""
        player.interior_x = player.interior_y = 0
        player.interior_aim = 0.0
        await send_json(session.websocket, _interior_state_payload(player))


async def process_passenger_action(session: ClientSession) -> None:
    """E-key passenger boarding without stealing or taking the driver seat."""
    p = session.player
    if p.interior_id or session.driving_vehicle_id or session.passenger_vehicle_id or session.riding_bicycle_id:
        return
    if int(getattr(p, "level", 0)) != 0:
        await send_json(session.websocket, {"type": "notice", "text": "No passenger car on this level."})
        return
    eligible = [
        car for car in traffic_vehicles
        if car.controlled_by != p.player_id
        and bool(car.controlled_by or car.npc_driver)
        and math.hypot(car.x - p.x, car.y - p.y) <= 118.0
    ]
    if not eligible:
        await send_json(session.websocket, {"type": "notice", "text": "No occupied car close enough for a passenger."})
        return
    car = min(eligible, key=lambda item: math.hypot(item.x - p.x, item.y - p.y))
    if abs(car.speed) > PASSENGER_BOARD_MAX_SPEED:
        await send_json(session.websocket, {"type": "notice", "text": "That car is moving too fast to board."})
        return
    if len(car.passenger_ids) >= PASSENGER_CAPACITY:
        await send_json(session.websocket, {"type": "notice", "text": "That car has no free passenger seats."})
        return
    if p.player_id not in car.passenger_ids:
        car.passenger_ids.append(p.player_id)
    reset_on_foot_actions(session)
    session.passenger_vehicle_id = car.vehicle_id
    p.in_vehicle = True
    p.vehicle_id = car.vehicle_id
    p.vehicle_kind = "car"
    p.vehicle_role = "passenger"
    p.x, p.y, p.aim = car.x, car.y, car.angle
    await send_json(session.websocket, {
        "type": "notice",
        "text": "Entered as a passenger. The driver controls the car; press T to exit.",
    })


async def process_car_action(session: ClientSession) -> None:
    """T-key mobility action for cars and bicycles."""
    p = session.player

    if p.interior_id:
        await send_json(session.websocket, {"type": "notice", "text": "Exit the building before using a vehicle."})
        return

    # A passenger has no steering authority and exits independently of the driver.
    if session.passenger_vehicle_id:
        car = next((c for c in traffic_vehicles if c.vehicle_id == session.passenger_vehicle_id), None)
        if car is None:
            session.passenger_vehicle_id = ""
            p.in_vehicle = False
            p.vehicle_id = ""
            p.vehicle_kind = ""
            p.vehicle_role = ""
            await send_json(session.websocket, {"type": "notice", "text": "Passenger vehicle lost."})
            return
        if abs(car.speed) > PASSENGER_EXIT_MAX_SPEED:
            await send_json(session.websocket, {"type": "notice", "text": "The car is moving too fast to get out."})
            return
        if p.player_id in car.passenger_ids:
            car.passenger_ids.remove(p.player_id)
        session.passenger_vehicle_id = ""
        p.in_vehicle = False
        p.vehicle_id = ""
        p.vehicle_kind = ""
        p.vehicle_role = ""
        offsets = (-math.pi / 2.0, math.pi / 2.0, math.pi)
        for off in offsets:
            ex = car.x + math.cos(car.angle + off) * 40.0
            ey = car.y + math.sin(car.angle + off) * 40.0
            if not blocked(ex, ey, ACTIVE_MAP, level=p.level):
                p.x, p.y = ex, ey
                break
        await send_json(session.websocket, {"type": "notice", "text": "Exited the passenger seat."})
        return

    # Exit a bicycle first if currently riding one.
    if session.riding_bicycle_id:
        bike = next((b for b in bicycles if b.bicycle_id == session.riding_bicycle_id), None)
        if bike is None:
            session.riding_bicycle_id = ""
            p.in_vehicle = False
            p.vehicle_id = ""
            p.vehicle_kind = ""
            p.vehicle_role = ""
            await send_json(session.websocket, {"type": "notice", "text": "Bicycle lost."})
            return
        if abs(bike.speed) > 42.0:
            await send_json(session.websocket, {"type": "notice", "text": "Slow down before getting off the bicycle."})
            return
        bike.controlled_by = ""
        bike.npc_rider = False
        bike.parked = True
        bike.route_index = -1
        bike.speed = 0.0
        session.riding_bicycle_id = ""
        p.in_vehicle = False
        p.vehicle_id = ""
        p.vehicle_kind = ""
        p.vehicle_role = ""
        ex = bike.x + math.cos(bike.angle + math.pi / 2.0) * 28.0
        ey = bike.y + math.sin(bike.angle + math.pi / 2.0) * 28.0
        if not blocked(ex, ey, ACTIVE_MAP, level=p.level):
            p.x, p.y = ex, ey
        await send_json(session.websocket, {"type": "notice", "text": "Got off bicycle."})
        return

    # Existing car exit path.
    if session.driving_vehicle_id:
        car = next((c for c in traffic_vehicles if c.vehicle_id == session.driving_vehicle_id), None)
        if car is None:
            session.driving_vehicle_id = ""
            p.in_vehicle = False
            p.vehicle_id = ""
            p.vehicle_kind = ""
            p.vehicle_role = ""
            await send_json(session.websocket, {"type": "notice", "text": "Vehicle lost."})
            return
        if abs(car.speed) > 70.0:
            await send_json(session.websocket, {"type": "notice", "text": "Slow down before getting out."})
            return
        p.in_vehicle = False
        p.vehicle_id = ""
        p.vehicle_kind = ""
        p.vehicle_role = ""
        session.driving_vehicle_id = ""
        car.controlled_by = ""
        car.npc_driver = False
        car.parked = True
        car.route_index = -1
        car.speed = 0.0
        offsets = (math.pi / 2.0, -math.pi / 2.0, math.pi)
        for off in offsets:
            ex = car.x + math.cos(car.angle + off) * 40.0
            ey = car.y + math.sin(car.angle + off) * 40.0
            if not blocked(ex, ey, ACTIVE_MAP, level=p.level):
                p.x, p.y = ex, ey
                break
        await send_json(session.websocket, {"type": "notice", "text": "Exited vehicle. It is now parked."})
        return

    # Player-controlled road vehicles are still a Level-0 system.  Multi-level
    # pedestrian traversal is authoritative now; vehicle-level routing will be
    # added with the later server traffic-AI pass rather than guessing across an
    # overpass and accidentally selecting a car underneath the player.
    if int(getattr(p, "level", 0)) != 0:
        await send_json(session.websocket, {"type": "notice", "text": "No enterable road vehicle on this level yet."})
        return

    # Choose the closest mobility object instead of always preferring cars.
    car = nearest_vehicle(p.x, p.y, radius=104.0)
    bike = nearest_bicycle(p.x, p.y, radius=90.0)
    car_d = math.hypot(car.x - p.x, car.y - p.y) if car is not None else float("inf")
    bike_d = math.hypot(bike.x - p.x, bike.y - p.y) if bike is not None else float("inf")

    if bike is not None and bike_d <= car_d:
        if bike.controlled_by and bike.controlled_by != p.player_id:
            await send_json(session.websocket, {"type": "notice", "text": "Someone else is riding that bicycle."})
            return
        if bike.npc_rider:
            if abs(bike.speed) > 36.0:
                await send_json(session.websocket, {"type": "notice", "text": "The cyclist is moving too fast to take the bicycle."})
                return
            _spawn_dismounted_cyclist(bike)
            text = "You took the bicycle from the cyclist."
        else:
            text = "You got on the bicycle."
        bike.controlled_by = p.player_id
        bike.npc_rider = False
        bike.parked = False
        session.riding_bicycle_id = bike.bicycle_id
        p.in_vehicle = True
        p.vehicle_id = bike.bicycle_id
        p.vehicle_kind = "bicycle"
        p.vehicle_role = "rider"
        p.x, p.y, p.aim = bike.x, bike.y, bike.angle
        await send_json(session.websocket, {"type": "notice", "text": text + "  W/S pedal/brake, A/D steer, T dismount."})
        return

    if car is None:
        await send_json(session.websocket, {"type": "notice", "text": "No car or bicycle close enough to enter."})
        return
    if car.controlled_by and car.controlled_by != p.player_id:
        if abs(car.speed) > PASSENGER_BOARD_MAX_SPEED:
            await send_json(session.websocket, {"type": "notice", "text": "That car is moving too fast to board."})
            return
        if len(car.passenger_ids) >= PASSENGER_CAPACITY:
            await send_json(session.websocket, {"type": "notice", "text": "That car has no free passenger seats."})
            return
        if p.player_id not in car.passenger_ids:
            car.passenger_ids.append(p.player_id)
        session.passenger_vehicle_id = car.vehicle_id
        p.in_vehicle = True
        p.vehicle_id = car.vehicle_id
        p.vehicle_kind = "car"
        p.vehicle_role = "passenger"
        p.x, p.y, p.aim = car.x, car.y, car.angle
        await send_json(session.websocket, {"type": "notice", "text": "Entered as a passenger. The driver controls the car; press T to exit."})
        return
    if car.npc_driver:
        chance = 0.82 if abs(car.speed) < 18.0 else (0.60 if abs(car.speed) < 55.0 else 0.28)
        if random.random() > chance:
            car.speed = max(car.speed, 85.0)
            await send_json(session.websocket, {"type": "notice", "text": "Carjacking failed - the driver accelerated away."})
            return
        _spawn_ejected_driver(car)
        text = "You pulled the driver out and stole the car."
    else:
        text = "You entered the parked car."

    car.controlled_by = p.player_id
    car.npc_driver = False
    car.parked = False
    session.driving_vehicle_id = car.vehicle_id
    p.in_vehicle = True
    p.vehicle_id = car.vehicle_id
    p.vehicle_kind = "car"
    p.vehicle_role = "driver"
    p.x, p.y, p.aim = car.x, car.y, car.angle
    await send_json(session.websocket, {"type": "notice", "text": text + "  W/S throttle, A/D steer, SPACE handbrake, SHIFT full throttle, T exit."})


async def load_account(phone: str, name: str, requested_appearance: dict | None = None) -> tuple[int, list[dict | None], dict, bool]:
    if USE_MYSQL:
        assert DB is not None
        return await asyncio.to_thread(DB.load_or_create_account, phone, name, requested_appearance)
    account = memory_accounts.get(phone)
    if account is None:
        appearance = normalize_character(requested_appearance)
        memory_accounts[phone] = {
            "cash": 200, "inventory": empty_inventory(), "name": name, "appearance": appearance
        }
        return 200, empty_inventory(), appearance, True
    account["name"] = name
    if requested_appearance is not None:
        account["appearance"] = normalize_character(requested_appearance)
    appearance = normalize_character(account.get("appearance"))
    return int(account["cash"]), [dict(x) if x else None for x in account["inventory"]], appearance, False


async def save_account(session: ClientSession) -> None:
    if USE_MYSQL:
        assert DB is not None
        await asyncio.to_thread(
            DB.save_player_state,
            session.phone,
            session.player.name,
            session.player.cash,
            session.inventory,
            session.player.appearance,
        )
    else:
        memory_accounts[session.phone] = {
            "cash": session.player.cash,
            "inventory": [dict(x) if x else None for x in session.inventory],
            "name": session.player.name,
            "appearance": normalize_character(session.player.appearance),
        }


async def save_and_sync(session: ClientSession) -> None:
    session.player.packages = inventory_count(session.inventory, "package")
    await save_account(session)
    await send_json(session.websocket, inventory_payload(session))


async def process_interaction(session: ClientSession) -> None:
    p = session.player
    pos = (p.x, p.y)
    fire_escape_level = request_grid_fire_escape(session)
    if fire_escape_level:
        await send_json(session.websocket, {
            "type": "notice",
            "text": f"Fire escape: {fire_escape_level.upper()} level",
        })
        return
    job_locations = ACTIVE_MAP.get("job_locations", []) or []
    supplier_locations = [
        row
        for row in job_locations if str(row.get("role", "")).lower() == "supplier"
    ] or [{"pos": ACTIVE_MAP["supplier_pos"], "level": 0}]

    if any(
        int(location.get("level", 0)) == int(getattr(p, "level", 0))
        and distance(pos, tuple(location.get("pos", [0.0, 0.0]))) <= INTERACT_DISTANCE
        for location in supplier_locations
    ):
        if p.cash < BUY_PRICE:
            text = f"Need ${BUY_PRICE}."
        elif inventory_weight(session.inventory) + float(ITEM_DEFS["package"]["weight_kg"]) > INVENTORY_MAX_WEIGHT_KG + 1e-9:
            text = "Too heavy for your inventory."
        elif not inventory_add(session.inventory, "package", 1):
            text = "Inventory full."
        else:
            p.cash -= BUY_PRICE
            try:
                await save_and_sync(session)
                text = f"Bought 1 package for ${BUY_PRICE}."
            except Exception as exc:
                # Undo the transaction if persistence failed.
                inventory_remove(session.inventory, "package", 1)
                p.cash += BUY_PRICE
                text = f"Purchase failed to save: {exc}"
        await send_json(session.websocket, {"type": "notice", "text": text})
        return

    now = time.monotonic()
    for target_id, (_, expires) in list(trade_offers.items()):
        if expires <= now:
            trade_offers.pop(target_id, None)

    # Pressing E accepts a live offer addressed to this player. The buyer has
    # explicit control; sellers cannot force another account to spend money.
    pending = trade_offers.get(p.player_id)
    if pending is not None:
        seller = clients.get(pending[0])
        compatible_room = (
            seller is not None
            and seller.player.interior_id == p.interior_id
            and int(getattr(seller.player, "level", 0)) == int(getattr(p, "level", 0))
        )
        close_enough = seller is not None and distance(pos, (seller.player.x, seller.player.y)) <= INTERACT_DISTANCE
        if seller is None or not compatible_room or not close_enough:
            trade_offers.pop(p.player_id, None)
        elif p.cash < SELL_PRICE:
            await send_json(session.websocket, {"type": "notice", "text": f"Need ${SELL_PRICE} to accept {seller.player.name}'s offer."})
            return
        elif inventory_count(seller.inventory, "package") <= 0:
            trade_offers.pop(p.player_id, None)
            await send_json(session.websocket, {"type": "notice", "text": "That seller no longer has a package."})
            return
        elif inventory_weight(session.inventory) + float(ITEM_DEFS["package"]["weight_kg"]) > INVENTORY_MAX_WEIGHT_KG + 1e-9 or not inventory_add(session.inventory, "package", 1):
            await send_json(session.websocket, {"type": "notice", "text": "Your inventory cannot hold that package."})
            return
        else:
            inventory_remove(seller.inventory, "package", 1)
            p.cash -= SELL_PRICE
            seller.player.cash += SELL_PRICE
            try:
                await save_and_sync(seller)
                await save_and_sync(session)
                trade_offers.pop(p.player_id, None)
                await send_json(seller.websocket, {"type": "notice", "text": f"{p.name} bought your package for ${SELL_PRICE}."})
                await send_json(session.websocket, {"type": "notice", "text": f"Bought 1 package from {seller.player.name} for ${SELL_PRICE}."})
            except Exception as exc:
                inventory_remove(session.inventory, "package", 1)
                inventory_add(seller.inventory, "package", 1)
                p.cash += SELL_PRICE
                seller.player.cash -= SELL_PRICE
                await send_json(session.websocket, {"type": "notice", "text": f"Player trade failed to save: {exc}"})
            return

    candidates: list[tuple[float, str, object]] = []
    for other in clients.values():
        if (other is session or other.player.in_vehicle or other.player.interior_id != p.interior_id
                or int(getattr(other.player, "level", 0)) != int(getattr(p, "level", 0))):
            continue
        d = distance(pos, (other.player.x, other.player.y))
        if d <= INTERACT_DISTANCE:
            candidates.append((d, "player", other))
    if not p.interior_id:
        for npc in npc_pedestrians:
            if int(getattr(npc, "level", 0)) != int(getattr(p, "level", 0)):
                continue
            d = distance(pos, (npc.x, npc.y))
            if d <= INTERACT_DISTANCE:
                # Dedicated buyer NPCs win ties over ambient pedestrians so the
                # job role visible to the player is also the transaction target.
                priority = 0 if npc.kind == "buyer" else 1
                candidates.append((d + priority * 0.001, "npc", npc))

    if candidates:
        _, kind, target = min(candidates, key=lambda row: row[0])
        if inventory_count(session.inventory, "package") <= 0:
            await send_json(session.websocket, {"type": "notice", "text": "You have no package to sell."})
            return
        if kind == "player":
            buyer = target
            trade_offers[buyer.player.player_id] = (p.player_id, now + 12.0)
            await send_json(session.websocket, {"type": "notice", "text": f"Offered 1 package to {buyer.player.name} for ${SELL_PRICE}."})
            await send_json(buyer.websocket, {"type": "notice", "text": f"{p.name} offers 1 package for ${SELL_PRICE}. Press E nearby to accept."})
            return

        inventory_remove(session.inventory, "package", 1)
        p.cash += SELL_PRICE
        try:
            await save_and_sync(session)
            target_name = "buyer" if getattr(target, "kind", "") == "buyer" else "pedestrian"
            text = f"Sold 1 package to a {target_name} for ${SELL_PRICE}."
        except Exception as exc:
            inventory_add(session.inventory, "package", 1)
            p.cash -= SELL_PRICE
            text = f"NPC sale failed to save: {exc}"
        await send_json(session.websocket, {"type": "notice", "text": text})
        return

    await send_json(session.websocket, {"type": "notice", "text": "Find a nearby player or pedestrian to sell to."})


async def process_chat(session: ClientSession, message: dict) -> None:
    now = time.monotonic()
    if now - session.last_chat_time < 0.65:
        return
    text = "".join(ch for ch in str(message.get("text", "")) if ch.isprintable()).strip()[:120]
    if not text:
        return
    session.last_chat_time = now
    scope = "whisper" if str(message.get("scope", "local")) == "whisper" else "local"
    payload = {
        "type": "chat",
        "scope": scope,
        "sender_id": session.player.player_id,
        "sender_name": session.player.name,
        "text": text,
    }
    async with clients_lock:
        online = list(clients.values())
    if scope == "whisper":
        target_name = safe_name(message.get("target", "")).casefold()
        target = next((other for other in online if other.player.name.casefold() == target_name), None)
        if target is None:
            await send_json(session.websocket, {"type": "notice", "text": "That friend is not online."})
            return
        payload["target_name"] = target.player.name
        recipients = {session.player.player_id: session, target.player.player_id: target}.values()
    elif session.player.interior_id:
        recipients = [
            other for other in online
            if other.player.interior_id == session.player.interior_id
        ]
    else:
        radius = max(120.0, float(ENGINE_SETTINGS.get("local_chat_radius_px", 850.0)))
        radius2 = radius * radius
        recipients = [
            other for other in online
            if not other.player.interior_id
            and (other.player.x - session.player.x) ** 2 + (other.player.y - session.player.y) ** 2 <= radius2
        ]
    await asyncio.gather(
        *(send_json(other.websocket, payload) for other in recipients),
        return_exceptions=True,
    )


async def sms_history(session: ClientSession) -> list[dict]:
    if USE_MYSQL:
        assert DB is not None
        return await asyncio.to_thread(DB.load_sms_messages, session.phone, 50)
    rows = []
    for row in memory_sms_messages[-100:]:
        if row["sender_phone"] != session.phone and row["recipient_phone"] != session.phone:
            continue
        rows.append({
            "id": int(row["id"]),
            "sender_name": row["sender_name"],
            "recipient_name": row["recipient_name"],
            "text": row["text"],
            "direction": "out" if row["sender_phone"] == session.phone else "in",
            "unread": row["recipient_phone"] == session.phone and not bool(row.get("read_by_recipient", False)),
            "created_at": row.get("created_at", "this session"),
        })
    return rows[-50:]


async def send_sms_history(session: ClientSession) -> None:
    try:
        messages = await sms_history(session)
    except Exception as exc:
        await send_json(session.websocket, {
            "type": "notice", "text": f"Messages could not load: {mysql_error_text(exc)}",
        })
        return
    await send_json(session.websocket, {"type": "sms_sync", "messages": messages})


async def mark_sms_read(session: ClientSession) -> None:
    try:
        if USE_MYSQL:
            assert DB is not None
            await asyncio.to_thread(DB.mark_sms_read, session.phone)
        else:
            for row in memory_sms_messages:
                if row["recipient_phone"] == session.phone:
                    row["read_by_recipient"] = True
    except Exception as exc:
        await send_json(session.websocket, {
            "type": "notice", "text": f"Message read state could not save: {mysql_error_text(exc)}",
        })


async def process_sms(session: ClientSession, message: dict) -> None:
    """Store a friend SMS first, then deliver it live when the recipient is online."""
    now = time.monotonic()
    if now - session.last_sms_time < 0.65:
        return
    text = " ".join(
        "".join(ch for ch in str(message.get("text", "")) if ch.isprintable()).split()
    )[:160]
    target_name = safe_name(message.get("target", ""))
    if not text or not target_name:
        await send_json(session.websocket, {"type": "notice", "text": "SMS format: /sms FriendName message"})
        return
    session.last_sms_time = now

    async with clients_lock:
        online = list(clients.values())
    target_session = next(
        (other for other in online if other.player.name.casefold() == target_name.casefold()),
        None,
    )
    target_phone = target_session.phone if target_session is not None else ""
    canonical_target = target_session.player.name if target_session is not None else target_name
    if not target_phone:
        if USE_MYSQL:
            assert DB is not None
            try:
                resolved = await asyncio.to_thread(DB.find_account_by_display_name, target_name)
            except Exception as exc:
                await send_json(session.websocket, {
                    "type": "notice", "text": f"SMS directory unavailable: {mysql_error_text(exc)}",
                })
                return
            if resolved is not None:
                target_phone, canonical_target = resolved
        else:
            resolved = next(
                ((phone, str(account.get("name", target_name))) for phone, account in memory_accounts.items()
                 if str(account.get("name", "")).casefold() == target_name.casefold()),
                None,
            )
            if resolved is not None:
                target_phone, canonical_target = resolved
    if not target_phone:
        await send_json(session.websocket, {"type": "notice", "text": f"No player account named {target_name}."})
        return
    if target_phone == session.phone:
        await send_json(session.websocket, {"type": "notice", "text": "Choose a friend other than yourself."})
        return

    try:
        if USE_MYSQL:
            assert DB is not None
            stored = await asyncio.to_thread(
                DB.create_sms_message,
                session.phone, target_phone, session.player.name, canonical_target, text,
            )
        else:
            stored = {
                "id": (int(memory_sms_messages[-1]["id"]) + 1) if memory_sms_messages else 1,
                "sender_name": session.player.name,
                "recipient_name": canonical_target,
                "text": text,
                "created_at": "this session",
            }
            memory_sms_messages.append({
                **stored, "sender_phone": session.phone, "recipient_phone": target_phone,
                "read_by_recipient": False,
            })
    except Exception as exc:
        await send_json(session.websocket, {"type": "notice", "text": f"SMS could not save: {mysql_error_text(exc)}"})
        return

    outgoing = {"type": "sms_sent", **stored, "direction": "out", "unread": False}
    incoming = {"type": "sms_received", **stored, "direction": "in", "unread": True}
    await send_json(session.websocket, outgoing)
    if target_session is not None:
        await send_json(target_session.websocket, incoming)


def _clean_report_text(raw: object, limit: int) -> str:
    text = "".join(ch for ch in str(raw or "") if ch.isprintable())
    return " ".join(text.split())[:limit].strip()


def _sanitize_bug_screenshot(raw: bytes) -> bytes:
    """Decode and re-encode a bounded PNG, stripping metadata and payloads."""
    if len(raw) > BUG_REPORT_MAX_SCREENSHOT_BYTES or not raw.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("screenshot is not a supported PNG")
    try:
        from PIL import Image, UnidentifiedImageError
    except ImportError as exc:
        raise ValueError("server screenshot validation is unavailable") from exc
    try:
        Image.MAX_IMAGE_PIXELS = 4_000_000
        with Image.open(BytesIO(raw)) as opened:
            if opened.format != "PNG":
                raise ValueError("screenshot is not a supported PNG")
            width, height = opened.size
            if width < 1 or height < 1 or width * height > 4_000_000:
                raise ValueError("screenshot dimensions are unsupported")
            opened.load()
            clean = opened.convert("RGB")
            clean.thumbnail((1280, 720))
            output = BytesIO()
            clean.save(output, format="PNG", optimize=True)
            data = output.getvalue()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValueError("screenshot could not be decoded") from exc
    if len(data) > BUG_REPORT_MAX_SCREENSHOT_BYTES:
        raise ValueError("sanitized screenshot is too large")
    return data


def _bug_report_json(row: dict, *, include_screenshot: bool = False) -> dict:
    """Return moderator-safe JSON without the private account hash."""
    result: dict = {}
    for key, value in row.items():
        if key == "reporter_account_hash":
            continue
        if key == "screenshot":
            if include_screenshot and value:
                result["screenshot_base64"] = base64.b64encode(bytes(value)).decode("ascii")
            continue
        if key == "context_json":
            try:
                result["context"] = json.loads(str(value or "{}"))
            except json.JSONDecodeError:
                result["context"] = {}
            continue
        if hasattr(value, "isoformat"):
            result[key] = value.isoformat()
        else:
            result[key] = value
    return result


async def process_bug_report(session: ClientSession, message: dict) -> None:
    """Validate and enqueue an untrusted player report for human moderation."""
    now = time.monotonic()
    if session.bug_reports_this_session >= BUG_REPORT_SESSION_LIMIT:
        await send_json(session.websocket, {
            "type": "bug_report_error",
            "text": "session report limit reached; keep the local backup",
        })
        return
    remaining = BUG_REPORT_COOLDOWN_SECONDS - (now - session.last_bug_report_time)
    if remaining > 0.0:
        await send_json(session.websocket, {
            "type": "bug_report_error",
            "text": f"please wait {max(1, int(math.ceil(remaining)))} seconds before another report",
        })
        return
    source_last = bug_report_source_times.get(session.bug_rate_key, -10_000.0)
    source_remaining = BUG_REPORT_SOURCE_COOLDOWN_SECONDS - (now - source_last)
    if session.bug_rate_key and source_remaining > 0.0:
        await send_json(session.websocket, {
            "type": "bug_report_error",
            "text": f"network report limit: wait {max(1, int(math.ceil(source_remaining)))} seconds",
        })
        return
    if not USE_MYSQL or DB is None:
        await send_json(session.websocket, {
            "type": "bug_report_error",
            "text": "the server review queue is unavailable",
        })
        return

    description = _clean_report_text(message.get("description"), 400)
    if len(description) < 5:
        await send_json(session.websocket, {
            "type": "bug_report_error",
            "text": "describe the problem with at least 5 characters",
        })
        return
    category = _clean_report_text(message.get("category"), 32).lower()
    allowed_categories = {"bug", "map_art", "art", "ai", "collision_nav", "other"}
    if category not in allowed_categories:
        category = "other"
    source = _clean_report_text(message.get("source"), 32) or "chat_/bug"
    build_version = _clean_report_text(message.get("build_version"), 160) or "unknown"
    raw_context = message.get("context")
    context = raw_context if isinstance(raw_context, dict) else {}
    context = {
        str(key)[:48]: _clean_report_text(value, 160)
        for key, value in list(context.items())[:24]
    }

    screenshot: bytes | None = None
    screenshot_sha256 = ""
    screenshot_text = str(message.get("screenshot_base64", ""))
    if screenshot_text:
        try:
            screenshot = base64.b64decode(screenshot_text, validate=True)
        except (binascii.Error, ValueError):
            await send_json(session.websocket, {"type": "bug_report_error", "text": "invalid screenshot data"})
            return
        try:
            screenshot = _sanitize_bug_screenshot(screenshot)
        except ValueError as exc:
            await send_json(session.websocket, {"type": "bug_report_error", "text": str(exc)})
            return
        screenshot_sha256 = hashlib.sha256(screenshot).hexdigest()

    player = session.player
    reporter_hash = hashlib.sha256(f"{BUG_REPORT_SALT}:{session.phone}".encode("utf-8")).hexdigest()
    try:
        report_id = await asyncio.to_thread(
            DB.create_bug_report,
            reporter_account_hash=reporter_hash,
            reporter_name=player.name,
            source=source,
            category=category,
            description=description,
            build_version=build_version,
            map_id=str(ACTIVE_MAP.get("id", ACTIVE_MAP_ID))[:96],
            map_name=str(ACTIVE_MAP.get("name", "Open Night"))[:160],
            world_x=float(player.x),
            world_y=float(player.y),
            level=int(player.level),
            in_vehicle=bool(player.in_vehicle),
            vehicle_id=str(player.vehicle_id)[:96],
            context=context,
            screenshot=screenshot,
            screenshot_sha256=screenshot_sha256,
        )
    except Exception as exc:
        print(f"Bug report storage failed: {mysql_error_text(exc)}", flush=True)
        await send_json(session.websocket, {
            "type": "bug_report_error",
            "text": "server storage failed; keep the local backup",
        })
        return
    session.last_bug_report_time = now
    session.bug_reports_this_session += 1
    if session.bug_rate_key:
        bug_report_source_times[session.bug_rate_key] = now
    await send_json(session.websocket, {
        "type": "bug_report_receipt",
        "report_id": int(report_id),
        "status": "pending",
    })


async def handle_bug_admin_session(websocket: ServerConnection, hello: dict) -> None:
    """Serve a token-authenticated, human-only moderation connection."""
    supplied = str(hello.get("token", ""))
    if not BUG_ADMIN_TOKEN or not hmac.compare_digest(supplied, BUG_ADMIN_TOKEN):
        await send_json(websocket, {"type": "bug_admin_error", "text": "moderator authentication failed"})
        await websocket.close(code=1008, reason="moderator authentication failed")
        return
    if not USE_MYSQL or DB is None:
        await send_json(websocket, {"type": "bug_admin_error", "text": "MySQL moderation queue unavailable"})
        await websocket.close(code=1011, reason="moderation queue unavailable")
        return
    await send_json(websocket, {"type": "bug_admin_ready"})
    async for raw in websocket:
        try:
            message = json.loads(raw)
        except json.JSONDecodeError:
            continue
        action = str(message.get("type", ""))
        try:
            if action == "bug_admin_list":
                status = str(message.get("status", "pending"))
                rows = await asyncio.to_thread(DB.list_bug_reports, status, int(message.get("limit", 100)))
                await send_json(websocket, {
                    "type": "bug_admin_list",
                    "status": status,
                    "reports": [_bug_report_json(row) for row in rows],
                })
            elif action == "bug_admin_detail":
                report_id = int(message.get("report_id", 0))
                row = await asyncio.to_thread(DB.get_bug_report, report_id)
                await send_json(websocket, {
                    "type": "bug_admin_detail",
                    "report": _bug_report_json(row, include_screenshot=True) if row else None,
                })
            elif action == "bug_admin_moderate":
                report_id = int(message.get("report_id", 0))
                decision = str(message.get("decision", ""))
                # A separate explicit confirmation value prevents accidental or
                # scripted approval from a malformed reviewer command.
                if str(message.get("confirm", "")) != str(report_id):
                    raise ValueError("explicit report confirmation is required")
                reviewed_by = _clean_report_text(message.get("reviewed_by"), 64) or "human-reviewer"
                review_note = _clean_report_text(message.get("review_note"), 500)
                changed = await asyncio.to_thread(
                    DB.moderate_bug_report, report_id, decision, reviewed_by, review_note,
                )
                row = await asyncio.to_thread(DB.get_bug_report, report_id)
                await send_json(websocket, {
                    "type": "bug_admin_moderated",
                    "changed": bool(changed),
                    "report": _bug_report_json(row, include_screenshot=decision == "approved") if row else None,
                })
            else:
                await send_json(websocket, {"type": "bug_admin_error", "text": "unknown moderator command"})
        except (TypeError, ValueError) as exc:
            await send_json(websocket, {"type": "bug_admin_error", "text": str(exc)[:200]})
        except Exception as exc:
            print(f"Bug moderation failed: {mysql_error_text(exc)}", flush=True)
            await send_json(websocket, {"type": "bug_admin_error", "text": "moderation storage operation failed"})


async def handle_message(session: ClientSession, raw: str) -> None:
    try:
        message = json.loads(raw)
    except json.JSONDecodeError:
        return

    msg_type = message.get("type")
    if msg_type == "input":
        try:
            ix = float(message.get("x", 0.0))
            iy = float(message.get("y", 0.0))
            aim = float(message.get("aim", 0.0))
        except (TypeError, ValueError):
            return
        ix, iy = normalize_input(ix, iy)
        session.input_x = max(-1.0, min(1.0, ix))
        session.input_y = max(-1.0, min(1.0, iy))
        session.aim = aim
        session.boost = bool(message.get("boost", False))
        session.handbrake = bool(message.get("handbrake", False)) and bool(session.driving_vehicle_id)
        session.crouch_requested = bool(message.get("crouch", False))
        if not session.crouch_requested:
            session.crouch_cancel_latched = False
        if session.passenger_vehicle_id:
            session.boost = False
            session.handbrake = False
        on_foot = not session.driving_vehicle_id and not session.passenger_vehicle_id and not session.riding_bicycle_id
        if on_foot:
            now = time.monotonic()
            if bool(message.get("prone_toggle", False)):
                request_player_prone_toggle(session, now)
            if bool(message.get("jump", False)):
                fire_escape_level = request_grid_fire_escape(session)
                if fire_escape_level:
                    await send_json(session.websocket, {
                        "type": "notice",
                        "text": f"Fire escape: {fire_escape_level.upper()} level",
                    })
                else:
                    request_player_jump(session, now)
            airborne = bool(session.jump_kind and now < session.jump_until)
            if airborne or session.prone or session.stand_delay_remaining > 0.0:
                session.crouching = False
            else:
                session.crouching = session.crouch_requested and not session.crouch_cancel_latched
            if session.crouching or session.prone or airborne:
                session.boost = False
        session.last_input_time = time.monotonic()
    elif msg_type == "interact":
        await process_interaction(session)
    elif msg_type == "car_action":
        await process_car_action(session)
    elif msg_type == "passenger_action":
        await process_passenger_action(session)
    elif msg_type == "vehicle_lights":
        car = next((item for item in traffic_vehicles if item.vehicle_id == session.driving_vehicle_id), None)
        if car is None:
            return
        action = str(message.get("action", ""))
        if action == "left":
            car.turn_signal = 0 if car.turn_signal == -1 else -1
        elif action == "right":
            car.turn_signal = 0 if car.turn_signal == 1 else 1
        elif action == "headlights":
            car.headlights = not car.headlights
    elif msg_type == "interior_enter":
        await process_interior_action(session, "enter", message)
    elif msg_type == "interior_move":
        await process_interior_action(session, "move", message)
    elif msg_type == "interior_exit":
        await process_interior_action(session, "exit", message)
    elif msg_type == "chat":
        await process_chat(session, message)
    elif msg_type == "sms_send":
        await process_sms(session, message)
    elif msg_type == "sms_request":
        await send_sms_history(session)
    elif msg_type == "sms_mark_read":
        await mark_sms_read(session)
    elif msg_type == "friend_sync":
        session.friend_names = normalize_friend_names(message.get("names", []))
    elif msg_type == "bug_report_submit":
        await process_bug_report(session, message)
    elif msg_type == "inventory_request":
        await send_json(session.websocket, inventory_payload(session))
    elif msg_type == "inventory_move":
        try:
            source = int(message.get("source"))
            target = int(message.get("target"))
        except (TypeError, ValueError):
            return
        if source == target or not (0 <= source < len(session.inventory)) or not (0 <= target < len(session.inventory)):
            return
        src = session.inventory[source]
        dst = session.inventory[target]
        if src is None:
            return

        before = [dict(slot) if slot else None for slot in session.inventory]
        if dst is None:
            session.inventory[target] = src
            session.inventory[source] = None
        elif dst.get("item_id") == src.get("item_id"):
            item_id = str(src["item_id"])
            stack_max = int(ITEM_DEFS[item_id]["stack_max"])
            room = stack_max - int(dst["quantity"])
            moved = min(room, int(src["quantity"]))
            dst["quantity"] += moved
            src["quantity"] -= moved
            if src["quantity"] <= 0:
                session.inventory[source] = None
        else:
            session.inventory[source], session.inventory[target] = dst, src
        try:
            await save_and_sync(session)
        except Exception as exc:
            session.inventory = before
            await send_json(session.websocket, {"type": "notice", "text": f"Inventory move failed to save: {exc}"})


def choose_safe_player_spawn(map_config: dict) -> tuple[float, float]:
    if GRID_RUNTIME_ACTIVE and GRID_WORLD is not None:
        return GRID_WORLD.choose_spawn("ground", PLAYER_RADIUS)
    """Return a guaranteed walkable login position.

    CSV/reference-map edits may move roads/buildings independently. A configured spawn
    is treated as a preferred point, not permission to place the player inside
    collision. If necessary we search outward on a compact grid for the nearest
    walkable position.
    """
    candidates = list(map_config.get("login_spawns") or map_config.get("spawns") or [[128.0, 128.0]])
    random.shuffle(candidates)
    for raw in candidates:
        try:
            x, y = float(raw[0]), float(raw[1])
        except (TypeError, ValueError, IndexError):
            continue
        if not blocked(x, y, map_config):
            return x, y

    # If all configured spawns became obstructed after a map-data edit, rescue
    # the first one instead of leaving the account immobilized.
    raw = candidates[0] if candidates else [128.0, 128.0]
    try:
        cx, cy = float(raw[0]), float(raw[1])
    except (TypeError, ValueError, IndexError):
        cx, cy = 128.0, 128.0
    step = 32.0
    for ring in range(1, 21):
        r = ring * step
        # Search the square perimeter; cardinal positions are naturally tested
        # early, which tends to keep the player on the intended street/sidewalk.
        offsets = []
        for i in range(-ring, ring + 1):
            offsets.extend(((i * step, -r), (i * step, r), (-r, i * step), (r, i * step)))
        for ox, oy in offsets:
            x, y = cx + ox, cy + oy
            if not blocked(x, y, map_config):
                print(f"! login spawn {cx:.0f},{cy:.0f} obstructed; relocated to {x:.0f},{y:.0f}", flush=True)
                return x, y
    # Last-resort clamp near the world origin. This should only be reachable for
    # a severely malformed map; validation should report the underlying issue.
    return max(PLAYER_RADIUS + 2.0, cx), max(PLAYER_RADIUS + 2.0, cy)


async def send_portable_map_if_needed(websocket: ServerConnection, hello: dict) -> None:
    transfer = ACTIVE_MAP_TRANSFER
    if not transfer:
        return
    digest = str(transfer["hash"])
    cached = {str(x) for x in (hello.get("map_cache_hashes") or [])}
    if digest in cached:
        await send_json(websocket, {"type":"map_transfer_cached","map_hash":digest})
        return
    blob = Path(transfer["path"]).read_bytes()
    raw_chunk = 48 * 1024
    total = (len(blob) + raw_chunk - 1) // raw_chunk
    await send_json(websocket, {"type":"map_transfer_begin","map_hash":digest,"display_name":transfer["display_name"],"size_bytes":len(blob),"chunks":total,"encoding":"base64+zip"})
    for index in range(total):
        part = blob[index*raw_chunk:(index+1)*raw_chunk]
        await send_json(websocket, {"type":"map_transfer_chunk","map_hash":digest,"index":index,"data":base64.b64encode(part).decode("ascii")})
    await send_json(websocket, {"type":"map_transfer_end","map_hash":digest,"chunks":total})


async def client_handler(websocket: ServerConnection) -> None:
    if len(clients) >= MAX_PLAYERS:
        await websocket.close(code=1013, reason="server full")
        return

    player_id = uuid.uuid4().hex[:8]
    session: ClientSession | None = None

    try:
        raw = await asyncio.wait_for(websocket.recv(), timeout=8.0)
        hello = json.loads(raw)
        if hello.get("type") == "probe":
            await send_json(websocket, server_info_payload(SERVER_NAME, ACTIVE_PORT, MAX_PLAYERS, ACTIVE_MAP))
            await websocket.close(code=1000, reason="probe complete")
            return
        if hello.get("type") == "bug_admin_hello":
            await handle_bug_admin_session(websocket, hello)
            return
        if hello.get("type") != "hello":
            await websocket.close(code=1008, reason="hello required")
            return

        client_version = str(hello.get("client_version", "")).strip()
        if client_version != SERVER_VERSION:
            shown = f"v{client_version}" if client_version else "an older build"
            await send_json(websocket, {
                "type": "login_error",
                "text": (
                    f"Version mismatch: this server requires Open Night v{SERVER_VERSION}, "
                    f"but your client reported {shown}. Run UPDATE_FRIEND_BUILD.bat and reconnect."
                ),
                "required_version": SERVER_VERSION,
                "client_version": client_version,
            })
            await websocket.close(code=1008, reason="client version mismatch")
            return

        phone = normalize_phone(hello.get("phone"))
        if phone is None:
            await send_json(websocket, {"type": "login_error", "text": "Enter a valid phone number (7-15 digits)."})
            await websocket.close(code=1008, reason="invalid phone")
            return

        # Prevent simultaneous sessions from racing writes to one account.
        async with clients_lock:
            if any(existing.phone == phone for existing in clients.values()):
                await send_json(websocket, {"type": "login_error", "text": "That phone-number account is already logged in."})
                await websocket.close(code=1008, reason="account already online")
                return

        name = safe_name(hello.get("name"))
        await send_portable_map_if_needed(websocket, hello)
        # The client only sends appearance when the user explicitly changed it
        # in the login customizer. Otherwise existing accounts retain the
        # server-stored look.
        requested_appearance = hello.get("appearance") if hello.get("appearance_changed") else None
        try:
            cash, inventory, appearance, created = await load_account(phone, name, requested_appearance)
        except Exception as exc:
            await send_json(websocket, {"type": "login_error", "text": f"Account database unavailable: {mysql_error_text(exc)}"})
            await websocket.close(code=1011, reason="database unavailable")
            return

        remote_address = getattr(websocket, "remote_address", None)
        remote_host = str(remote_address[0]) if isinstance(remote_address, tuple) and remote_address else "unknown"
        rate_key = hashlib.sha256(f"{BUG_REPORT_SALT}:{remote_host}".encode("utf-8")).hexdigest()
        duplicate_after_load = False
        async with clients_lock:
            if any(existing.phone == phone for existing in clients.values()):
                duplicate_after_load = True
            else:
                occupied = {
                    existing.apartment_interior_id for existing in clients.values()
                    if existing.apartment_interior_id
                }
                spawn_x, spawn_y = choose_safe_player_spawn(ACTIVE_MAP)
                login_house = house_login_state(ACTIVE_MAP, phone, occupied)
                interior_id = ""
                interior_x = interior_y = 0
                interior_aim = 0.0
                if login_house is not None:
                    interior_id, spawn_x, spawn_y, interior_x, interior_y = login_house
                    interior_aim = -math.pi / 2.0
                else:
                    overflow_spawn = overflow_exterior_spawn(ACTIVE_MAP, phone)
                    if overflow_spawn is not None:
                        spawn_x, spawn_y = overflow_spawn
                player = PlayerState(
                    player_id=player_id,
                    name=name,
                    x=spawn_x,
                    y=spawn_y,
                    cash=int(cash),
                    packages=inventory_count(inventory, "package"),
                    appearance=normalize_character(appearance),
                    interior_id=interior_id,
                    interior_x=interior_x,
                    interior_y=interior_y,
                    interior_aim=interior_aim,
                )
                session = ClientSession(
                    websocket=websocket,
                    player=player,
                    phone=phone,
                    inventory=inventory,
                    apartment_interior_id=interior_id,
                    bug_rate_key=rate_key,
                )
                clients[player_id] = session
            server_population = len(clients)
        if duplicate_after_load:
            await send_json(websocket, {"type": "login_error", "text": "That phone-number account is already logged in."})
            await websocket.close(code=1008, reason="account already online")
            return
        housing_capacity = len(blank_house_interiors(ACTIVE_MAP))
        print_machine_status()

        await send_json(websocket, {
            "type": "welcome",
            "id": player_id,
            "player": player.public_dict(),
            "map": network_map_payload(ACTIVE_MAP),
            "game_mode": dict(ACTIVE_GAME_MODE),
            "server_version": SERVER_VERSION,
            "server_population": server_population,
            "housing_capacity": housing_capacity,
            "housing_overflow": max(0, server_population - housing_capacity),
            "server_metrics": SERVER_TICK_METRICS.public_dict(),
            "account": {
                "phone_masked": masked_phone(phone),
                "created": created,
                "apartment": {
                    "interior_id": player.interior_id,
                    "floor": 1,
                    "label": f"1st Floor - {player.name}'s Apartment",
                } if player.interior_id else None,
            },
            "inventory": inventory,
            "inventory_weight_kg": round(inventory_weight(inventory), 3),
        })
        if player.interior_id:
            await send_json(websocket, _interior_state_payload(player))
        await send_json(websocket, {
            "type": "notice",
            "text": (
                f"{'New account created' if created else 'Account loaded'} ({masked_phone(phone)}). "
                + (
                    f"Housing is full ({server_population}/{housing_capacity}); you spawned outside an apartment. "
                    if not player.interior_id and housing_capacity > 0 else ""
                )
                + "I/TAB inventory, E interact, T car/bicycle, M world map."
            ),
        })
        await send_sms_history(session)
        print(f"+ {player.name} [{player_id}] account {masked_phone(phone)} connected", flush=True)

        async for raw in websocket:
            await handle_message(session, raw)

    except (ConnectionClosed, asyncio.TimeoutError, json.JSONDecodeError):
        pass
    finally:
        if session is not None:
            # Never strand a vehicle in a permanently player-controlled state when
            # a client disconnects or crashes.
            if session.driving_vehicle_id:
                car = next((c for c in traffic_vehicles if c.vehicle_id == session.driving_vehicle_id), None)
                if car is not None:
                    car.controlled_by = ""
                    car.npc_driver = False
                    car.parked = True
                    car.route_index = -1
                    car.speed = 0.0
                session.driving_vehicle_id = ""
            if session.passenger_vehicle_id:
                car = next((c for c in traffic_vehicles if c.vehicle_id == session.passenger_vehicle_id), None)
                if car is not None and session.player.player_id in car.passenger_ids:
                    car.passenger_ids.remove(session.player.player_id)
                session.passenger_vehicle_id = ""
            if session.riding_bicycle_id:
                bike = next((b for b in bicycles if b.bicycle_id == session.riding_bicycle_id), None)
                if bike is not None:
                    bike.controlled_by = ""
                    bike.npc_rider = False
                    bike.parked = True
                    bike.route_index = -1
                    bike.speed = 0.0
                session.riding_bicycle_id = ""
            session.player.in_vehicle = False
            session.player.vehicle_id = ""
            session.player.vehicle_kind = ""
            session.player.vehicle_role = ""
            session.player.interior_id = ""
            try:
                await save_account(session)
            except Exception as exc:
                print(f"! save failed for {session.player.name}: {mysql_error_text(exc)}")
            async with clients_lock:
                clients.pop(player_id, None)
            print_machine_status()
            print(f"- {session.player.name} [{player_id}] disconnected", flush=True)


async def simulation_loop() -> None:
    tick_dt = 1.0 / SERVER_TICK_RATE
    ambient_interval = 1.0 / AMBIENT_SIM_RATE
    ambient_accumulator = 0.0
    ambient_tick_index = 0
    next_tick = time.monotonic()
    while True:
        now = time.monotonic()
        if now < next_tick:
            await asyncio.sleep(next_tick - now)
        current = time.monotonic()
        dt = min(0.05, max(0.0, current - (next_tick - tick_dt)))
        next_tick += tick_dt
        if current - next_tick > 0.25:
            next_tick = current + tick_dt
        tick_work_started = time.perf_counter()

        async with clients_lock:
            sessions = list(clients.values())
        housing_capacity = len(blank_house_interiors(ACTIVE_MAP))
        vehicle_by_id = {car.vehicle_id: car for car in traffic_vehicles}
        bicycle_by_id = {bike.bicycle_id: bike for bike in bicycles}
        for session in sessions:
            if current - session.last_input_time > 0.5:
                session.input_x = session.input_y = 0.0
                session.boost = False
                session.handbrake = False
            p = session.player
            finish_expired_player_jump(session, current)

            if p.interior_id:
                session.input_x = session.input_y = 0.0
                session.boost = False
                reset_on_foot_actions(session)
                continue

            if session.passenger_vehicle_id:
                car = vehicle_by_id.get(session.passenger_vehicle_id)
                if car is None or p.player_id not in car.passenger_ids:
                    session.passenger_vehicle_id = ""
                    p.in_vehicle = False
                    p.vehicle_id = ""
                    p.vehicle_kind = ""
                    p.vehicle_role = ""
                else:
                    reset_on_foot_actions(session)
                    p.x, p.y = car.x, car.y
                    p.aim = car.angle
                    p.level = 0
                    continue

            if session.riding_bicycle_id:
                bike = bicycle_by_id.get(session.riding_bicycle_id)
                if bike is None:
                    session.riding_bicycle_id = ""
                    p.in_vehicle = False
                    p.vehicle_id = ""
                    p.vehicle_kind = ""
                    p.vehicle_role = ""
                else:
                    reset_on_foot_actions(session)
                    steer = max(-1.0, min(1.0, session.input_x))
                    throttle = max(-1.0, min(1.0, -session.input_y))
                    max_forward = float(BICYCLE_AI.get("player_max_speed_px_s", 190.0))
                    accel = float(BICYCLE_AI.get("player_acceleration_px_s2", 175.0))
                    brake = float(BICYCLE_AI.get("player_brake_px_s2", 260.0))
                    turn_rate = float(BICYCLE_AI.get("player_turn_rate", 2.8))
                    drag = 52.0
                    if throttle > 0.05:
                        bike.speed = min(max_forward, bike.speed + accel * throttle * dt)
                    elif throttle < -0.05:
                        bike.speed = max(0.0, bike.speed - brake * (-throttle) * dt)
                    else:
                        bike.speed = max(0.0, bike.speed - drag * dt)
                    if bike.speed > 4.0 and abs(steer) > 0.02:
                        bike.angle += steer * turn_rate * min(1.0, 0.25 + bike.speed / 75.0) * dt
                    nx = bike.x + math.cos(bike.angle) * bike.speed * dt
                    ny = bike.y + math.sin(bike.angle) * bike.speed * dt
                    # Bicycle-to-bicycle overlap is intentionally lightweight, but
                    # the full bicycle body remains solid against cars/map hazards.
                    blocked_mobility = _bicycle_map_blocked(bike,nx,ny,bike.angle) or _bicycle_hits_vehicle(bike,nx,ny,bike.angle)
                    if blocked_mobility:
                        bike.speed *= 0.25
                    else:
                        bike.x, bike.y = nx, ny
                    bike.parked = False
                    p.x, p.y = bike.x, bike.y
                    p.aim = bike.angle
                    continue

            if session.driving_vehicle_id:
                car = vehicle_by_id.get(session.driving_vehicle_id)
                if car is None:
                    session.driving_vehicle_id = ""
                    p.in_vehicle = False
                    p.vehicle_id = ""
                    p.vehicle_kind = ""
                    p.vehicle_role = ""
                else:
                    reset_on_foot_actions(session)
                    # Arcade car physics: acceleration, braking, reverse, speed-
                    # dependent steering and inertia. The server remains authoritative.
                    steer = max(-1.0, min(1.0, session.input_x))
                    throttle = max(-1.0, min(1.0, -session.input_y))  # W=forward
                    # Client speed display uses 0.18 mph per px/s. Shift is the
                    # explicit full-throttle control; boosted player cars top out
                    # at the configured 88 mph while ordinary throttle remains calmer.
                    mph_per_px_s = float(VEHICLE_SETTINGS.get("mph_per_px_s", 0.18))
                    boost_top_mph = float(VEHICLE_SETTINGS.get("player_boost_max_mph", 88.0))
                    cruise_top_mph = float(VEHICLE_SETTINGS.get("player_cruise_max_mph", 62.0))
                    max_forward = (boost_top_mph if session.boost else cruise_top_mph) / max(0.01, mph_per_px_s)
                    max_reverse = float(VEHICLE_SETTINGS.get("player_reverse_px_s", 112.0))
                    accel = float(VEHICLE_SETTINGS.get("player_boost_accel_px_s2", 340.0) if session.boost else VEHICLE_SETTINGS.get("player_accel_px_s2", 220.0))
                    accel *= max(0.75, min(1.20, car.speed_factor))
                    reverse_accel = float(VEHICLE_SETTINGS.get("player_reverse_accel_px_s2", 145.0))
                    brake = float(VEHICLE_SETTINGS.get("player_brake_px_s2", 390.0))
                    drag = float(VEHICLE_SETTINGS.get("player_drag_px_s2", 92.0))

                    if session.handbrake:
                        _apply_player_handbrake(car, dt)
                    elif throttle > 0.05:
                        car.brake_lights = car.speed < -1.0
                        if car.speed < 0.0:
                            car.speed = min(0.0, car.speed + brake * dt)
                        else:
                            car.speed = min(max_forward, car.speed + accel * throttle * dt)
                    elif throttle < -0.05:
                        car.brake_lights = car.speed > 1.0
                        if car.speed > 12.0:
                            car.speed = max(0.0, car.speed - brake * (-throttle) * dt)
                        else:
                            car.speed = max(-max_reverse, car.speed - reverse_accel * (-throttle) * dt)
                    else:
                        car.brake_lights = False
                        if car.speed > 0.0:
                            car.speed = max(0.0, car.speed - drag * dt)
                        elif car.speed < 0.0:
                            car.speed = min(0.0, car.speed + drag * dt)

                    speed_abs = abs(car.speed)
                    old_angle = car.angle
                    proposed_angle = old_angle
                    if speed_abs > 3.0 and abs(steer) > 0.02:
                        steering_grip = min(1.0, 0.22 + speed_abs / 95.0)
                        high_speed_reduction = max(0.42, 1.0 - speed_abs / 620.0)
                        direction = 1.0 if car.speed >= 0.0 else -1.0
                        turn_rate = float(VEHICLE_SETTINGS.get("player_turn_rate", 2.75))
                        turn_rate *= player_signal_turn_multiplier(car, steer)
                        proposed_angle += steer * turn_rate * steering_grip * high_speed_reduction * direction * dt

                    # Steering rotates the body around its front axle rather than
                    # around the sprite/collision centre. This makes the rear swing
                    # visibly and produces the requested top-down car handling.
                    rotated_center_x, rotated_center_y = _front_axle_rotated_center(car, proposed_angle)
                    dx = math.cos(proposed_angle) * car.speed * dt
                    dy = math.sin(proposed_angle) * car.speed * dt
                    nx, ny = rotated_center_x + dx, rotated_center_y + dy
                    map_clear = not _vehicle_map_blocked(car, nx, ny, proposed_angle)
                    bicycle_clear = not _vehicle_hits_bicycle(car, nx, ny, proposed_angle)
                    vehicle_clear = not _vehicle_hits_vehicle(car, nx, ny, proposed_angle)
                    if map_clear and bicycle_clear and not vehicle_clear:
                        vehicle_clear = _push_blocking_vehicles(
                            car, nx, ny, proposed_angle,
                            max(12.0, abs(car.speed) * dt + 8.0),
                        )
                    if map_clear and vehicle_clear and bicycle_clear:
                        car.x, car.y, car.angle = nx, ny, proposed_angle
                    else:
                        # v0.9 arcade collision recovery: try a short glancing slide
                        # before killing momentum. This prevents player cars being
                        # pinned squarely into building corners after one impact.
                        impact_speed = car.speed
                        deflected = False
                        direction = 1.0 if impact_speed >= 0.0 else -1.0
                        last_deflection = float(getattr(car, "last_player_collision_deflection_at", -1e9))
                        can_deflect = current - last_deflection >= 0.25
                        for deflect_angle in ((0.04, -0.04, 0.07, -0.07) if can_deflect else ()):
                            candidate_angle = _player_collision_deflection_angle(old_angle, deflect_angle, direction)
                            slide = impact_speed * dt * 0.45
                            sx = car.x + math.cos(candidate_angle) * slide
                            sy = car.y + math.sin(candidate_angle) * slide
                            if (_vehicle_map_blocked(car, sx, sy, candidate_angle)
                                    or _vehicle_hits_vehicle(car, sx, sy, candidate_angle)
                                    or _vehicle_hits_bicycle(car, sx, sy, candidate_angle)):
                                continue
                            car.x, car.y, car.angle = sx, sy, candidate_angle
                            car.speed = impact_speed * 0.42
                            car.last_player_collision_deflection_at = current
                            deflected = True
                            break
                        if not deflected:
                            # A small rebound leaves the next input tick able to steer
                            # away instead of trapping the car at exactly zero speed.
                            car.angle = old_angle
                            car.speed = -impact_speed * 0.10
                    car.parked = False
                    p.x, p.y = car.x, car.y
                    p.aim = car.angle
                    continue
            input_moving = math.hypot(session.input_x, session.input_y) > 0.05
            airborne = bool(session.jump_kind and current < session.jump_until)
            movement_blocked_for_stand = False
            if current < session.forced_prone_until:
                session.prone = True
                session.crouching = False
                session.boost = False
                movement_blocked_for_stand = True
            elif not airborne:
                if not session.prone and session.stand_delay_remaining <= 0.0:
                    session.crouching = session.crouch_requested and not session.crouch_cancel_latched
                if input_moving and (session.prone or session.crouching):
                    if session.stand_delay_remaining <= 0.0:
                        session.stand_delay_remaining = MOVEMENT_STAND_DELAY_SECONDS
                    session.stand_delay_remaining = max(0.0, session.stand_delay_remaining - dt)
                    if session.stand_delay_remaining <= 0.0:
                        session.prone = False
                        session.crouching = False
                        session.crouch_cancel_latched = bool(session.crouch_requested)
                    else:
                        movement_blocked_for_stand = True
                        session.boost = False
                elif not session.prone and not session.crouching:
                    session.stand_delay_remaining = 0.0

            if airborne:
                dx = session.jump_velocity_x * dt
                dy = session.jump_velocity_y * dt
                drag = 0.85 if session.jump_kind == "double_jump" else 1.15
                velocity_decay = max(0.0, 1.0 - dt * drag)
                session.jump_velocity_x *= velocity_decay
                session.jump_velocity_y *= velocity_decay
                session.boost = False
            elif movement_blocked_for_stand:
                dx = dy = 0.0
            else:
                walk_speed = max(0.0, float(MOVEMENT_SETTINGS.get("walk_speed_px_per_second", PLAYER_SPEED)))
                sprint_mult = float(MOVEMENT_SETTINGS.get("sprint_multiplier", 3.0)) if session.boost else 1.0
                dx = session.input_x * walk_speed * sprint_mult * dt
                dy = session.input_y * walk_speed * sprint_mult * dt
            current_level = int(getattr(p, "level", 0))
            water_probe_x, water_probe_y = p.x + dx, p.y + dy
            wading = (not GRID_RUNTIME_ACTIVE) and current_level == 0 and (
                point_in_water(p.x, p.y, ACTIVE_MAP)
                or point_in_water(water_probe_x, water_probe_y, ACTIVE_MAP)
            ) and not (
                point_near_road(p.x, p.y, ACTIVE_MAP, extra=PLAYER_RADIUS, bridge_only=True, level=0)
                or point_near_road(water_probe_x, water_probe_y, ACTIVE_MAP, extra=PLAYER_RADIUS, bridge_only=True, level=0)
            )
            if wading:
                dx *= WATER_WALK_SPEED_MULTIPLIER
                dy *= WATER_WALK_SPEED_MULTIPLIER
                session.boost = False
            movement_start_x, movement_start_y = p.x, p.y
            if GRID_RUNTIME_ACTIVE and GRID_WORLD is not None and current_level in {0, 1}:
                if current_level == 1:
                    p.x, p.y = GRID_WORLD.move_circle_roof(p.x, p.y, dx, dy, PLAYER_RADIUS)
                else:
                    p.x, p.y = GRID_WORLD.move_circle(
                        "ground", p.x, p.y, dx, dy, PLAYER_RADIUS
                    )
            else:
                p.x, p.y = move_with_collisions(
                    p.x, p.y, dx, dy, ACTIVE_MAP, level=current_level, allow_water=True
                )
            previous_level = int(getattr(p, "level", 0))
            next_level = resolve_level_transition(
                p.x,
                p.y,
                previous_level,
                ACTIVE_MAP,
                previous_x=movement_start_x,
                previous_y=movement_start_y,
            )
            if GRID_RUNTIME_ACTIVE and previous_level in {0, 1}:
                # Grid Ground and roofs own their fire-escape transitions. Do not
                # let the retired vector connector table switch levels under them.
                next_level = previous_level
            p.level = next_level
            if next_level != previous_level and LAYER_TRANSITION_JUMP_SECONDS > 0.0:
                # Optional authored transition pose. v0.9 defaults this to zero so
                # automatic ramps/bridges never masquerade as a player jump.
                session.jump_until = max(
                    session.jump_until,
                    time.monotonic() + LAYER_TRANSITION_JUMP_SECONDS,
                )
            p.aim = session.aim

        signal_time = time.time()
        current_mono = time.monotonic()
        update_player_vehicle_impacts(sessions, current_mono)
        update_npc_runovers(current_mono)
        update_hydrants(current_mono)
        ambient_accumulator = min(ambient_interval * 2.0, ambient_accumulator + dt)
        if ambient_accumulator >= ambient_interval:
            ambient_dt = ambient_accumulator
            ambient_accumulator = 0.0
            update_traffic(ambient_dt, sessions, signal_time)
            update_bicycles(ambient_dt, sessions)
            update_npcs(ambient_dt, sessions, ambient_tick_index, signal_time)
            displace_low_speed_npcs()
            ambient_tick_index += 1
        SERVER_TICK_METRICS.record_tick(time.perf_counter() - tick_work_started)


async def snapshot_loop() -> None:
    """Send per-player snapshots using a chunk-bucket interest index.

    v2.3 filtered by chunk radius but still rescanned every entity for every
    connected player. v2.4 builds the spatial buckets once per snapshot and then
    touches only the nearby 3x3/5x5 interest cells for each recipient.
    """
    interval = 1.0 / SNAPSHOT_RATE
    last_map_roster_push = 0.0
    while True:
        await asyncio.sleep(interval)
        async with clients_lock:
            sessions = list(clients.values())
        server_time = time.time()
        push_map_roster = server_time - last_map_roster_push >= 1.0 / MAP_ROSTER_RATE
        if push_map_roster:
            last_map_roster_push = server_time
        all_lights = traffic_light_states(ACTIVE_MAP, server_time)
        radius = max(0, int(ACTIVE_MAP.get("interest_radius_chunks", NETWORK_INTEREST_RADIUS_CHUNKS)))

        player_buckets: dict[tuple[int,int], list[ClientSession]] = {}
        vehicle_buckets: dict[tuple[int,int], list[TrafficVehicle]] = {}
        npc_buckets: dict[tuple[int,int], list[NPCPedestrian]] = {}
        bicycle_buckets: dict[tuple[int,int], list[BicycleState]] = {}
        blood_buckets: dict[tuple[int,int], list[BloodStain]] = {}
        hydrant_buckets: dict[tuple[int,int], list[HydrantState]] = {}
        light_buckets: dict[tuple[int,int], list[dict]] = {}

        for other in sessions:
            player_buckets.setdefault(world_to_chunk(other.player.x, other.player.y, ACTIVE_MAP), []).append(other)
        for car in traffic_vehicles:
            vehicle_buckets.setdefault(world_to_chunk(car.x, car.y, ACTIVE_MAP), []).append(car)
        for npc in npc_pedestrians:
            npc_buckets.setdefault(world_to_chunk(npc.x, npc.y, ACTIVE_MAP), []).append(npc)
        for bike in bicycles:
            bicycle_buckets.setdefault(world_to_chunk(bike.x, bike.y, ACTIVE_MAP), []).append(bike)
        for stain in blood_stains:
            blood_buckets.setdefault(world_to_chunk(stain.x, stain.y, ACTIVE_MAP), []).append(stain)
        for hydrant in hydrants.values():
            hydrant_buckets.setdefault(world_to_chunk(hydrant.x, hydrant.y, ACTIVE_MAP), []).append(hydrant)
        for signal in ACTIVE_MAP.get("traffic_signals", []):
            pos = signal.get("pos", [0, 0])
            light_buckets.setdefault(world_to_chunk(float(pos[0]), float(pos[1]), ACTIVE_MAP), []).append(signal)

        sends = []
        for session in sessions:
            pcx, pcy = world_to_chunk(session.player.x, session.player.y, ACTIVE_MAP)
            prx, pry = world_to_region(session.player.x, session.player.y, ACTIVE_MAP)
            visible_players = []
            visible_vehicles = []
            visible_npcs = []
            visible_bicycles = []
            visible_blood = []
            visible_hydrants = []
            visible_lights = {}

            for cy in range(max(0, pcy-radius), pcy+radius+1):
                for cx in range(max(0, pcx-radius), pcx+radius+1):
                    key = (cx, cy)
                    for other in player_buckets.get(key, ()):
                        pdata = other.player.public_dict()
                        if other.player.in_vehicle:
                            pdata["pose"] = "idle"
                        elif time.monotonic() < other.jump_until:
                            pdata["pose"] = other.jump_kind if other.jump_kind in {"jump", "double_jump"} else "jump"
                        elif other.prone:
                            pdata["pose"] = "prone"
                        elif other.crouching:
                            pdata["pose"] = "crouch"
                        elif other.boost and math.hypot(other.input_x, other.input_y) > 0.05:
                            pdata["pose"] = "run"
                        else:
                            pdata["pose"] = "idle"
                        visible_players.append(pdata)
                    visible_vehicles.extend(car.public_dict() for car in vehicle_buckets.get(key, ()))
                    visible_npcs.extend(npc.public_dict() for npc in npc_buckets.get(key, ()))
                    visible_bicycles.extend(bike.public_dict() for bike in bicycle_buckets.get(key, ()))
                    snapshot_mono = time.monotonic()
                    visible_blood.extend(stain.public_dict(snapshot_mono) for stain in blood_buckets.get(key, ()))
                    visible_hydrants.extend(hydrant.public_dict(snapshot_mono) for hydrant in hydrant_buckets.get(key, ()))
                    for signal in light_buckets.get(key, ()):
                        sid = str(signal.get("id"))
                        visible_lights[sid] = bool(all_lights.get(sid, False))

            payload = {
                "type": "snapshot",
                "players": visible_players,
                "vehicles": visible_vehicles,
                "npcs": visible_npcs,
                "bicycles": visible_bicycles,
                "blood_stains": visible_blood,
                "hydrants": visible_hydrants,
                "traffic_lights": visible_lights,
                "server_time": server_time,
                "server_population": len(sessions),
                "housing_capacity": housing_capacity,
                "housing_overflow": max(0, len(sessions) - housing_capacity),
                "server_metrics": SERVER_TICK_METRICS.public_dict(),
                "chunk": [pcx, pcy],
                "chunk_id": chunk_label(pcx, pcy),
                "interest_radius": radius,
                "region": [prx, pry],
                "region_id": region_label(prx, pry),
            }
            if push_map_roster:
                # Apartment residents are absent from a recipient's global map
                # and directory unless they are self, a saved friend, or the
                # recipient is standing beside that apartment's buzzer.
                map_players = [resident.player.map_marker_dict() for resident in sessions]
                apartment_directory = []
                mutual_friends = sorted(
                    resident.player.name
                    for resident in sessions
                    if resident is not session
                    and resident.player.name.casefold() in session.friend_names
                    and session.player.name.casefold() in resident.friend_names
                )
                for resident in sessions:
                    is_resident = bool(resident.apartment_interior_id)
                    if is_resident and _can_view_apartment_residency(session, resident):
                        apartment_directory.append({
                            "interior_id": resident.apartment_interior_id,
                            "floor": 1,
                            "resident_name": resident.player.name,
                            "label": f"1st Floor - {resident.player.name}'s Apartment",
                        })
                payload["map_players"] = map_players
                payload["apartment_directory"] = apartment_directory
                payload["mutual_friends"] = mutual_friends
            sends.append(send_json(session.websocket, payload))
        if sends:
            await asyncio.gather(*sends, return_exceptions=True)


async def main(host: str, port: int, server_name: str, discovery: bool = True) -> None:
    global SERVER_NAME, ACTIVE_PORT
    SERVER_NAME = str(server_name)
    ACTIVE_PORT = int(port)
    loop = asyncio.get_running_loop()
    discovery_transport = None
    if discovery:
        discovery_transport, _ = await loop.create_datagram_endpoint(
            lambda: DiscoveryProtocol(server_name, port, MAX_PLAYERS, ACTIVE_MAP),
            local_addr=(host, port),
            allow_broadcast=True,
        )

    print("\n" + "=" * 70)
    print(f"  {server_name}")
    print("=" * 70)
    print(f"  Map:           {ACTIVE_MAP['name']} ({ACTIVE_MAP['id']})")
    print(f"  Game mode:     {ACTIVE_GAME_MODE['name']} ({ACTIVE_GAME_MODE['id']})")
    if ACTIVE_MAP_TRANSFER:
        print(f"  Portable map:  {ACTIVE_MAP_TRANSFER['hash'][:12]}… / {ACTIVE_MAP_TRANSFER['size_bytes']} bytes cached package")
    print(f"  Players:       0/{MAX_PLAYERS}")
    print(f"  Game address:  ws://{host}:{port}")
    print(f"  LAN discovery: {'enabled' if discovery else 'disabled'}")
    print(f"  Persistence:   {'MySQL' if USE_MYSQL else 'memory (development only)'}")
    moving_count = sum(1 for c in traffic_vehicles if not c.parked)
    parked_count = sum(1 for c in traffic_vehicles if c.parked)
    print(f"  Civilian cars: {moving_count} moving + {parked_count} parked")
    print(f"  Bicycles:      {sum(1 for b in bicycles if b.npc_rider)} cyclists + {sum(1 for b in bicycles if b.parked)} parked")
    print(f"  Pedestrians:   {len(npc_pedestrians)}")
    print(f"  Vehicle sprite library: {vehicle_count()} normal sprites")
    print("=" * 70)
    print("Server is running. Press Ctrl+C to stop.\n", flush=True)
    print_machine_status()

    try:
        async with serve(
            client_handler,
            host,
            port,
            ping_interval=20,
            ping_timeout=20,
            max_size=3 * 1024 * 1024,
        ):
            await asyncio.gather(simulation_loop(), snapshot_loop())
    finally:
        if discovery_transport is not None:
            discovery_transport.close()


def _prompt_text(label: str, default: str) -> str:
    value = input(f"{label} [{default}]: ").strip()
    return value or default


def _prompt_secret(label: str, default: str = "") -> str:
    shown = "configured" if default else "blank"
    value = getpass.getpass(f"{label} [{shown}]: ")
    return value if value else default


def _prompt_int(label: str, default: int, minimum: int, maximum: int) -> int:
    while True:
        raw = input(f"{label} [{default}]: ").strip()
        if not raw:
            return default
        try:
            value = int(raw)
        except ValueError:
            print("  Enter a whole number.")
            continue
        if minimum <= value <= maximum:
            return value
        print(f"  Enter a value from {minimum} to {maximum}.")


def _prompt_yes_no(label: str, default: bool = True) -> bool:
    suffix = "Y/n" if default else "y/N"
    while True:
        raw = input(f"{label} [{suffix}]: ").strip().lower()
        if not raw:
            return default
        if raw in {"y", "yes"}:
            return True
        if raw in {"n", "no"}:
            return False
        print("  Enter Y or N.")


def _prompt_map(default_id: str = DEFAULT_MAP_ID) -> str:
    map_ids = list(MAPS)
    print("\nMAP")
    for index, map_id in enumerate(map_ids, start=1):
        cfg = MAPS[map_id]
        default_marker = "  < default" if map_id == default_id else ""
        print(f"  {index}. {cfg['name']:<20} {cfg['description']}{default_marker}")
    default_number = map_ids.index(default_id) + 1 if default_id in map_ids else 1
    while True:
        raw = input(f"Select map [1-{len(map_ids)}] [{default_number}]: ").strip()
        if not raw:
            return map_ids[default_number - 1]
        try:
            index = int(raw)
        except ValueError:
            index = -1
        if 1 <= index <= len(map_ids):
            return map_ids[index - 1]
        print("  Select one of the numbered maps.")


def interactive_setup() -> argparse.Namespace:
    print("\n" + "=" * 70)
    print("               PYTHON MMO - SERVER LAUNCHER")
    print("=" * 70)
    print("Press Enter to keep any value shown in [brackets].\n")

    name = _prompt_text("Server name", SERVER_NAME)
    port = _prompt_int("Port (LAN auto-detect range 8765-8795)", PORT, 8765, 8795)
    max_players = _prompt_int("Maximum players", MAX_PLAYERS, 1, 2000)
    map_id = _prompt_map(DEFAULT_MAP_ID)
    game_mode_id = DEFAULT_GAME_MODE_ID
    discovery = _prompt_yes_no("Advertise this server on the LAN", True)
    mysql_enabled = _prompt_yes_no("Use MySQL account/inventory persistence", True)

    db_host = os.getenv("PYMMO_DB_HOST", "127.0.0.1")
    db_port = int(os.getenv("PYMMO_DB_PORT", "3306"))
    db_name = os.getenv("PYMMO_DB_NAME", "pymmo")
    db_user = os.getenv("PYMMO_DB_USER", "root")
    db_password = os.getenv("PYMMO_DB_PASSWORD", "")
    if mysql_enabled:
        print("\nMYSQL")
        db_host = _prompt_text("MySQL host", db_host)
        db_port = _prompt_int("MySQL port", db_port, 1, 65535)
        db_name = _prompt_text("Database name", db_name)
        db_user = _prompt_text("MySQL user", db_user)
        db_password = _prompt_secret("MySQL password", db_password)

    print("\nCONFIGURATION")
    print(f"  Server:       {name}")
    print(f"  Port:         {port}")
    print(f"  Max players:  {max_players}")
    print(f"  Map:          {MAPS[map_id]['name']}")
    print(f"  Game mode:    {GAME_MODES[game_mode_id]['name']}")
    print(f"  LAN listing:  {'Yes' if discovery else 'No'}")
    print(f"  Persistence:  {'MySQL ' + db_user + '@' + db_host + ':' + str(db_port) + '/' + db_name if mysql_enabled else 'Memory only'}")
    print()
    if not _prompt_yes_no("Launch server", True):
        raise SystemExit("Server launch cancelled.")

    return argparse.Namespace(
        host=HOST, port=port, name=name, max_players=max_players, map=map_id, mode=game_mode_id,
        no_discovery=not discovery, memory_db=not mysql_enabled,
        db_host=db_host, db_port=db_port, db_name=db_name, db_user=db_user,
        db_password=db_password,
    )


def cli_main() -> None:
    global MAX_PLAYERS, ACTIVE_MAP_ID, ACTIVE_MAP, DB, USE_MYSQL, TRAFFIC_COUNT, ACTIVE_MAP_TRANSFER, ACTIVE_GAME_MODE

    import sys
    # Load the packaged screenshot-derived authoritative map. Portable .map files
    # may explicitly replace it per server instance; no live map service is queried.
    reload_maps()
    if len(sys.argv) == 1:
        from server_launcher import launch_server_manager
        launch_server_manager()
        return

    parser = argparse.ArgumentParser(description="Python MMO authoritative server")
    parser.add_argument("--host", default=HOST, help="Bind address")
    parser.add_argument("--port", type=int, default=PORT, help="WebSocket + UDP discovery port")
    parser.add_argument("--name", default=SERVER_NAME, help="Server name shown in launcher")
    parser.add_argument("--max-players", type=int, default=MAX_PLAYERS)
    parser.add_argument("--traffic", type=int, default=TRAFFIC_DEFAULT_COUNT, help="Number of server-authoritative civilian traffic cars")
    parser.add_argument("--map", choices=list(MAPS), default=DEFAULT_MAP_ID)
    parser.add_argument("--mode", choices=list(GAME_MODES), default=DEFAULT_GAME_MODE_ID, help="Server gameplay ruleset")
    parser.add_argument("--map-file", default="", help="Load a portable .map file and distribute its data/textures to client caches")
    parser.add_argument("--no-discovery", action="store_true")
    parser.add_argument("--memory-db", action="store_true", help="Development-only: disable MySQL persistence")
    parser.add_argument("--db-host", default=os.getenv("PYMMO_DB_HOST", os.getenv("MYSQLHOST", "127.0.0.1")))
    parser.add_argument("--db-port", type=int, default=int(os.getenv("PYMMO_DB_PORT", os.getenv("MYSQLPORT", "3306"))))
    parser.add_argument("--db-name", default=os.getenv("PYMMO_DB_NAME", os.getenv("MYSQLDATABASE", "pymmo")))
    parser.add_argument("--db-user", default=os.getenv("PYMMO_DB_USER", os.getenv("MYSQLUSER", "root")))
    parser.add_argument("--db-password", default=os.getenv("PYMMO_DB_PASSWORD", os.getenv("MYSQLPASSWORD", "")))
    args = parser.parse_args()

    if not 1 <= args.port <= 65535:
        parser.error("--port must be from 1 to 65535")

    MAX_PLAYERS = max(1, min(2000, args.max_players))
    ACTIVE_GAME_MODE = get_game_mode(args.mode)
    TRAFFIC_COUNT = max(0, min(120, int(args.traffic)))
    ACTIVE_MAP_TRANSFER = None
    if args.map_file:
        try:
            ACTIVE_MAP = load_portable_map(Path(args.map_file), verify_hashes=True)
            ACTIVE_MAP_ID = str(ACTIVE_MAP.get("id", "portable_map"))
            ACTIVE_MAP_TRANSFER = build_transfer_bundle(Path(args.map_file))
        except Exception as exc:
            parser.error(f"Could not load --map-file: {exc}")
    else:
        ACTIVE_MAP_ID = args.map
        ACTIVE_MAP = get_map(ACTIVE_MAP_ID)
    map_errors = validate_map(ACTIVE_MAP)
    if map_errors and ACTIVE_MAP_TRANSFER:
        print(f"\nPortable map loaded with {len(map_errors)} legacy geometry validator warning(s).")
        for error in map_errors[:12]: print(" -", error)
        if len(map_errors) > 12: print(f" - ... {len(map_errors)-12} more (portable generator validation remains authoritative for this imported map)")
    elif map_errors:
        print("\nMapfile validation failed:")
        for error in map_errors: print(" -", error)
        raise SystemExit(3)
    USE_MYSQL = not args.memory_db

    if USE_MYSQL:
        config = DatabaseConfig(
            host=args.db_host, port=args.db_port, database=args.db_name,
            user=args.db_user, password=args.db_password,
        )
        DB = InventoryDatabase(config)
        print("\nConnecting to MySQL and checking schema...")
        try:
            DB.initialize()
            if str(os.getenv("PYMMO_RESET_DB_ON_PATCH", "false")).lower() in {"1","true","yes","on"}:
                patch_id=os.getenv("PYMMO_PATCH_ID", SERVER_VERSION)
                if DB.reset_for_patch(patch_id):
                    print(f"Prototype persistence reset for new patch {patch_id}.")
                else:
                    print(f"Prototype persistence retained for patch {patch_id} restart.")
        except Exception as exc:
            print(f"MySQL startup failed: {mysql_error_text(exc)}")
            print("Check the MySQL service, host/port, username/password, and CREATE DATABASE permissions.")
            raise SystemExit(2)
        print("MySQL persistence ready.")
        if BUG_ADMIN_TOKEN:
            print("Human-moderated bug-report queue ready.")
        else:
            print("WARNING: bug reports can be stored, but PYMMO_BUG_ADMIN_TOKEN is not configured for review.")

    if GRID_RUNTIME_ACTIVE:
        # Old entity routes were authored against the retired vector map and may
        # cross new buildings. Keep the first playable grid milestone honest by
        # suppressing them until grid-native routes/spawns are authored.
        print("Grid Ground runtime active: legacy traffic/NPC surface entities disabled.")
    else:
        initialize_traffic(TRAFFIC_COUNT)
        initialize_parked_vehicles()
        initialize_bicycles()
        initialize_npcs()
        initialize_hydrants()

    try:
        asyncio.run(main(args.host, args.port, args.name, discovery=not args.no_discovery))
    except KeyboardInterrupt:
        print("\nServer stopped.")
    except OSError as exc:
        print(f"\nCould not start server: {exc}")
        print("The selected port may already be in use, or Windows Firewall/network permissions may need attention.")


if __name__ == "__main__":
    cli_main()
