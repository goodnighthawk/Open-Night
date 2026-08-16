from __future__ import annotations

import csv
import shutil
from copy import deepcopy
from pathlib import Path

from portable_paths import ensure_shared_layout

ROOT = Path(__file__).resolve().parents[1]
LOCAL_CONFIG_PATH = ROOT / "config" / "game_settings.csv"
CONFIG_PATH = ensure_shared_layout()["config"] / "game_settings.csv"
if not CONFIG_PATH.exists() and LOCAL_CONFIG_PATH.exists():
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(LOCAL_CONFIG_PATH, CONFIG_PATH)

DEFAULTS = {
    "camera": {
        "lookahead_enabled": True,
        "walking_max_px": 220.0,
        "driving_max_px": 320.0,
        "deadzone_px": 70.0,
        "full_lookahead_mouse_distance_px": 480.0,
        "smoothing_per_second": 8.5,
        "return_smoothing_per_second": 11.0,
        "rotation_enabled": True,
        "rotation_default_degrees": 0.0,
        "rotation_sensitivity_deg_per_px": 0.32,
        "rotation_snap_degrees": 0.0,
        "zoom_default": 0.85,
        "zoom_min": 0.55,
        "zoom_max": 2.0,
        "zoom_step": 0.10,
        "center_player_when_rotated": True,
    },
    "controls": {
        "movement_aim_independent": True,
        "local_player_camera_facing": True,
        "camera_relative_movement": True,
        "body_follows_movement": True,
        "idle_body_realign_camera": True,
    },
    "movement": {
        "walk_speed_px_per_second": 92.5,
        "sprint_multiplier": 3.0,
        "sprint_animation_rate_multiplier": 1.85,
        "sprint_gait_width_multiplier": 1.48,
        "jump_forward_speed_px_per_second": 570.0,
        "jump_duration_seconds": 0.75,
        "double_jump_window_seconds": 0.55,
        "double_jump_forward_speed_px_per_second": 313.3333333333333,
        "double_jump_duration_seconds": 0.95,
        "movement_stand_delay_seconds": 1.0,
        "water_walk_speed_multiplier": 0.28,
    },
    "vehicle": {
        "mph_per_px_s": 0.18,
        "player_cruise_max_mph": 62.0,
        "player_boost_max_mph": 88.0,
        "player_accel_px_s2": 220.0,
        "player_boost_accel_px_s2": 340.0,
        "player_reverse_px_s": 112.0,
        "player_reverse_accel_px_s2": 145.0,
        "player_brake_px_s2": 390.0,
        "player_drag_px_s2": 92.0,
        "player_turn_rate": 2.75,
        "player_front_axle_offset_ratio": 0.36,
    },
    "engine": {"ai_profile_version": 2, "client_profile_version": 282},
    "debug": {"show_camera_lookahead": False},
    "render": {
        "player_scale": 1,
        "jump_scale_multiplier": 1.35,
        "jump_lift_px": 10,
        "double_jump_scale_multiplier": 1.50,
        "double_jump_lift_px": 14,
        "npc_scale": 1,
        "cyclist_rider_scale": 1,
        "fractional_zoom_filter": "smooth",
        "camera_pixel_snap": True,
        "filtered_rotation": True,
    },
    "traffic": {
        "default_moving_cars": 28,
        "wait_priority_gain": 1.0,
        "stuck_recycle_seconds": 8.0,
        "recycle_player_clearance_px": 900.0,
        "max_wait_priority": 15.0,
        "follow_time_seconds": 0.14,
    },
    "npc": {
        "pedestrians_per_route": 3,
        "personal_space_px": 22.0,
        "active_radius_px": 1800.0,
        "far_update_hz": 5.0,
        "runover_min_speed_mph": 30.0,
    },
    "bicycle": {
        "ai_cyclists_per_route": 3,
        "parked_bikes": 28,
        "ai_speed_px_s": 118.0,
        "player_max_speed_px_s": 190.0,
        "player_acceleration_px_s2": 175.0,
        "player_brake_px_s2": 260.0,
        "player_turn_rate": 3.6,
    },
}


def _parse_value(raw: str, value_type: str):
    t = (value_type or "str").strip().lower()
    value = (raw or "").strip()
    if t == "bool":
        return value.lower() in {"1", "true", "yes", "y", "on"}
    if t == "int":
        return int(float(value))
    if t == "float":
        return float(value)
    return value


def _csv_rows(path: Path) -> list[dict]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            return [dict(r) for r in csv.DictReader(handle)]
    except OSError:
        return []


def _migrate_v2_ai_profile(shared_path: Path) -> None:
    """One-time migration of old shared AI tuning to the v2.0 flow profile.

    Camera/UI/user preferences remain untouched. Only traffic/NPC/bicycle tuning
    plus the new car turn-rate baseline are migrated. Subsequent user edits win.
    """
    if shared_path == LOCAL_CONFIG_PATH:
        return
    shared_rows = _csv_rows(shared_path)
    revision = 0
    for row in shared_rows:
        if str(row.get("section", "")).strip() == "engine" and str(row.get("key", "")).strip() == "ai_profile_version":
            try:
                revision = int(float(str(row.get("value", "0"))))
            except ValueError:
                revision = 0
            break
    if revision >= 2:
        return
    local_rows = _csv_rows(LOCAL_CONFIG_PATH)
    migrate_sections = {"traffic", "npc", "bicycle"}
    migrate_keys = {("vehicle", "player_turn_rate"), ("engine", "ai_profile_version")}
    desired = [r for r in local_rows if str(r.get("section", "")).strip() in migrate_sections or (str(r.get("section", "")).strip(), str(r.get("key", "")).strip()) in migrate_keys]
    fields = ["section", "key", "value", "type", "notes"]
    by_key = {(str(r.get("section", "")).strip(), str(r.get("key", "")).strip()): r for r in shared_rows}
    for row in desired:
        key = (str(row.get("section", "")).strip(), str(row.get("key", "")).strip())
        if key in by_key:
            by_key[key].update(row)
        else:
            shared_rows.append(dict(row))
            by_key[key] = shared_rows[-1]
    try:
        shared_path.parent.mkdir(parents=True, exist_ok=True)
        with shared_path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            for row in shared_rows:
                writer.writerow({name: row.get(name, "") for name in fields})
    except OSError:
        pass


def _migrate_v26_client_profile(shared_path: Path) -> None:
    """Apply the current camera/movement contract to persistent shared settings.

    The migration preserves unrelated user settings while retaining the camera-rotation
    performance controls, camera-relative walking, and the shared preview/server
    action contract. Vehicle controls remain raw. Profile 282 halves absolute walk/run
    speed and reduces double-jump forward propulsion to one third of its prior value.
    """
    if shared_path == LOCAL_CONFIG_PATH:
        return
    shared_rows = _csv_rows(shared_path)
    revision = 0
    for row in shared_rows:
        if str(row.get("section", "")).strip() == "engine" and str(row.get("key", "")).strip() == "client_profile_version":
            try:
                revision = int(float(str(row.get("value", "0"))))
            except ValueError:
                revision = 0
            break
    if revision >= 282:
        return
    shared_rows = [
        row for row in shared_rows
        if (str(row.get("section", "")).strip(), str(row.get("key", "")).strip())
        != ("movement", "sprint_double_tap_window_seconds")
    ]
    local_rows = _csv_rows(LOCAL_CONFIG_PATH)
    migrate_keys = {
        ("camera", "zoom_default"),
        ("controls", "local_player_camera_facing"),
        ("controls", "camera_relative_movement"),
        ("controls", "body_follows_movement"),
        ("controls", "idle_body_realign_camera"),
        ("render", "fractional_zoom_filter"),
        ("render", "camera_pixel_snap"),
        ("render", "filtered_rotation"),
        ("render", "fast_rotation_while_dragging"),
        ("render", "defer_25d_rotation_while_dragging"),
        ("movement", "walk_speed_px_per_second"),
        ("movement", "sprint_multiplier"),
        ("movement", "sprint_animation_rate_multiplier"),
        ("movement", "sprint_gait_width_multiplier"),
        ("movement", "jump_forward_speed_px_per_second"),
        ("movement", "jump_duration_seconds"),
        ("movement", "double_jump_window_seconds"),
        ("movement", "double_jump_forward_speed_px_per_second"),
        ("movement", "double_jump_duration_seconds"),
        ("movement", "movement_stand_delay_seconds"),
        ("render", "jump_scale_multiplier"),
        ("render", "jump_lift_px"),
        ("render", "double_jump_scale_multiplier"),
        ("render", "double_jump_lift_px"),
        ("engine", "client_profile_version"),
    }
    desired = [r for r in local_rows if (str(r.get("section", "")).strip(), str(r.get("key", "")).strip()) in migrate_keys]
    fields = ["section", "key", "value", "type", "notes"]
    by_key = {(str(r.get("section", "")).strip(), str(r.get("key", "")).strip()): r for r in shared_rows}
    for row in desired:
        key = (str(row.get("section", "")).strip(), str(row.get("key", "")).strip())
        if key in by_key:
            by_key[key].update(row)
        else:
            shared_rows.append(dict(row))
            by_key[key] = shared_rows[-1]
    try:
        shared_path.parent.mkdir(parents=True, exist_ok=True)
        with shared_path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            for row in shared_rows:
                writer.writerow({name: row.get(name, "") for name in fields})
    except OSError:
        pass


def load_settings(path: Path = CONFIG_PATH) -> dict:
    """Load flat CSV rows into a nested settings dictionary.

    Human-edited settings live in CSV so tuning can be done in a spreadsheet or
    text editor. Missing/malformed rows fall back to DEFAULTS.
    """
    settings = deepcopy(DEFAULTS)
    _migrate_v2_ai_profile(Path(path))
    _migrate_v26_client_profile(Path(path))
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                section = str(row.get("section", "")).strip()
                key = str(row.get("key", "")).strip()
                if not section or not key:
                    continue
                try:
                    parsed = _parse_value(str(row.get("value", "")), str(row.get("type", "str")))
                except (TypeError, ValueError):
                    continue
                settings.setdefault(section, {})[key] = parsed
    except OSError:
        pass
    return settings


def set_setting_value(section: str, key: str, value, path: Path = CONFIG_PATH) -> None:
    """Persist one setting while preserving the CSV's human-editable structure."""
    rows = []
    fieldnames = ["section", "key", "value", "type", "notes"]
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames:
                fieldnames = list(reader.fieldnames)
            rows = [dict(r) for r in reader]
    except OSError:
        pass
    found = False
    for row in rows:
        if str(row.get("section", "")).strip() == section and str(row.get("key", "")).strip() == key:
            row["value"] = str(value).lower() if isinstance(value, bool) else str(value)
            found = True
            break
    if not found:
        kind = "bool" if isinstance(value, bool) else ("int" if isinstance(value, int) else "float" if isinstance(value, float) else "str")
        rows.append({"section": section, "key": key, "value": str(value).lower() if isinstance(value, bool) else str(value), "type": kind, "notes": "Updated from in-game settings"})
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({name: row.get(name, "") for name in fieldnames})