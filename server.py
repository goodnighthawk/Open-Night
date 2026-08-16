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
from versioning import GAME_VERSION, version_label

HOST = "0.0.0.0"
PORT = 8765
SERVER_NAME = version_label()
MAX_PLAYERS = 128
DISCOVERY_MAGIC = "PYMMO_DISCOVER_V1"
SERVER_VERSION = GAME_VERSION
BUG_REPORT_MAX_SCREENSHOT_BYTES = 1_500_000
BUG_REPORT_COOLDOWN_SECONDS = 45.0
BUG_REPORT_SOURCE_COOLDOWN_SECONDS = 15.0
BUG_REPORT_SESSION_LIMIT = 10
BUG_ADMIN_TOKEN = os.getenv("PYMMO_BUG_ADMIN_TOKEN", "").strip()
BUG_REPORT_SALT = os.getenv("PYMMO_BUG_REPORT_SALT", BUG_ADMIN_TOKEN or "open-night-local").strip()

ACTIVE_MAP_ID = DEFAULT_MAP_ID
ACTIVE_MAP = get_map(ACTIVE_MAP_ID)
ACTIVE_MAP_TRANSFER = None
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
LAYER_TRANSITION_JUMP_SECONDS = max(0.1, float(MOVEMENT_SETTINGS.get("layer_transition_jump_seconds", 0.65)))
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
