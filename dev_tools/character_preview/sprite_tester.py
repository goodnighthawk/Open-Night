from __future__ import annotations

import argparse
import csv
import math
import os
import sys
import tempfile
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path


APP_NAME = "OPEN NIGHT // Character Movement Preview"
WINDOW_SIZE = (1280, 760)
WORLD_RECT = (18, 18, 850, 724)
WORLD_SIZE = (2600, 2200)
CELL = 256
DRAW_ORDER = ("body", "top", "bottom", "footwear", "head", "accessory")
DIRECTIONS = ("north", "northeast", "east", "southeast", "south", "southwest", "west", "northwest")
SLOT_LABELS = {
    "body": "Body",
    "head": "Head / hair",
    "top": "Top",
    "bottom": "Bottom",
    "footwear": "Footwear",
    "accessory": "Accessory",
}
FLUID_PRESET_PROFILES = {
    "street_blue": "tshirt_blue_curly",
    "masked_olive": "hoodie_olive_fade_mask",
    "night_jacket": "jacket_black_ponytail_shades",
    "cap_red": "tshirt_red_cap_shorts",
    "rider": "rider_fullface",
}


class PackError(RuntimeError):
    pass


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def find_pack_root(path: Path) -> Path:
    if (path / "config" / "paired_parts.csv").is_file():
        return path
    matches = list(path.glob("*/config/paired_parts.csv"))
    if len(matches) == 1:
        return matches[0].parent.parent
    raise PackError(f"No unique config/paired_parts.csv found beneath {path}")


def safe_extract(zip_path: Path, destination: Path) -> None:
    destination_resolved = destination.resolve()
    with zipfile.ZipFile(zip_path) as archive:
        for info in archive.infolist():
            target = (destination / info.filename).resolve()
            try:
                target.relative_to(destination_resolved)
            except ValueError as exc:
                raise PackError(f"Unsafe ZIP member: {info.filename}") from exc
        archive.extractall(destination)


@dataclass
class LoadedSource:
    root: Path
    temp_dir: tempfile.TemporaryDirectory[str] | None = None

    def close(self) -> None:
        if self.temp_dir is not None:
            self.temp_dir.cleanup()
            self.temp_dir = None


def load_source(path: Path) -> LoadedSource:
    path = path.expanduser().resolve()
    if path.is_dir():
        return LoadedSource(find_pack_root(path))
    if path.is_file() and path.suffix.lower() == ".zip":
        temp = tempfile.TemporaryDirectory(prefix="sprite_tester_pack_")
        destination = Path(temp.name)
        safe_extract(path, destination)
        return LoadedSource(find_pack_root(destination), temp)
    raise PackError(f"Choose the sprite-pack ZIP or its extracted folder: {path}")


def default_pack_candidates(app_dir: Path) -> list[Path]:
    filename = "dual_camera_character_customization_set.zip"
    game_root = app_dir.parents[1]
    return [
        game_root / "assets" / "characters" / "master_dual_camera",
        app_dir / "sprite_packs" / filename,
        app_dir / filename,
        app_dir.parent / filename,
        app_dir / "dual_camera_character_customization_set",
        app_dir.parent / "dual_camera_character_customization_set",
    ]


class SpritePack:
    def __init__(self, pygame_module, source: LoadedSource):
        self.pg = pygame_module
        self.source = source
        self.root = source.root
        self.parts: dict[tuple[str, str, str], str] = {}
        self.choices_by_slot: dict[str, list[str]] = {}
        self.rules: dict[tuple[str, str, str], bool] = {}
        self.presets: list[dict[str, str]] = []
        self.animations: dict[str, dict[str, str]] = {}
        self.actions: dict[tuple[str, str], str] = {}
        self.fluid: dict[tuple[str, str, str], dict[str, str]] = {}
        self.camera_settings: dict[str, str] = {}
        self.movement_settings: dict[str, str] = {}
        self.idle_settings: dict[str, str] = {}
        self._images: dict[str, object] = {}
        self._load_catalogs()

    def close(self) -> None:
        self.source.close()

    def _load_catalogs(self) -> None:
        pair_rows = read_csv(self.root / "config" / "paired_parts.csv")
        choices: dict[str, set[str]] = {}
        for row in pair_rows:
            if row.get("paired") != "true" or row.get("selectable") != "true":
                continue
            slot, part_id = row["slot"], row["part_id"]
            choices.setdefault(slot, set()).add(part_id)
            for mode in ("isometric", "topdown"):
                relative = row[f"{mode}_sheet"]
                path = self.root / relative
                if not path.is_file():
                    raise PackError(f"Missing paired sheet: {relative}")
                self.parts[(mode, slot, part_id)] = relative
        for slot, values in choices.items():
            self.choices_by_slot[slot] = sorted(values)
        self.choices_by_slot.setdefault("accessory", []).insert(0, "none")

        for row in read_csv(self.root / "config" / "compatibility_rules.csv"):
            self.rules[(row["rule_type"], row["left_id"], row["right_id"])] = row["allowed"] == "true"
        self.presets = read_csv(self.root / "config" / "customization_presets.csv")
        for row in read_csv(self.root / "config" / "animations.csv"):
            self.animations[row["animation"]] = row
        for row in read_csv(self.root / "config" / "action_sheets.csv"):
            self.actions[(row["camera_mode"], row["action"])] = row["sheet"]
        fluid_path = self.root / "config" / "fluid_animations.csv"
        if fluid_path.is_file():
            for row in read_csv(fluid_path):
                self.fluid[(row["camera_mode"], row["profile_id"], row["animation"])] = row
        camera_path = self.root / "config" / "camera_rotation.csv"
        if camera_path.is_file():
            self.camera_settings = {row["setting"]: row["value"] for row in read_csv(camera_path)}
        movement_path = self.root / "config" / "movement_settings.csv"
        if movement_path.is_file():
            self.movement_settings = {row["setting"]: row["value"] for row in read_csv(movement_path)}
        idle_path = self.root / "config" / "idle_settings.csv"
        if idle_path.is_file():
            self.idle_settings = {row["setting"]: row["value"] for row in read_csv(idle_path)}

        if not self.presets:
            raise PackError("The pack has no customization presets")
        valid, reason = self.validate(self.presets[0])
        if not valid:
            raise PackError(f"First preset is invalid: {reason}")

    def validate(self, selected: dict[str, str]) -> tuple[bool, str]:
        for slot in DRAW_ORDER:
            part_id = selected.get(slot, "none")
            if part_id != "none" and not all((mode, slot, part_id) in self.parts for mode in ("isometric", "topdown")):
                return False, f"{slot}:{part_id} is not paired"
        checks = (
            ("head_top", selected.get("head", ""), selected.get("top", "")),
            ("accessory_head", selected.get("accessory", "none"), selected.get("head", "")),
        )
        for key in checks:
            if key in self.rules and not self.rules[key]:
                return False, f"Incompatible: {key[1]} + {key[2]}"
        return True, "Valid paired appearance"

    def preset(self, index: int) -> dict[str, str]:
        row = self.presets[index % len(self.presets)]
        return {slot: row.get(slot, "none") for slot in DRAW_ORDER}

    def preset_name(self, index: int) -> str:
        return self.presets[index % len(self.presets)]["preset_id"]

    def matching_profile(self, selected: dict[str, str]) -> str | None:
        for row in self.presets:
            if all(selected.get(slot, "none") == row.get(slot, "none") for slot in DRAW_ORDER):
                return FLUID_PRESET_PROFILES.get(row["preset_id"])
        return None

    def matching_preset(self, selected: dict[str, str]) -> str | None:
        for row in self.presets:
            if all(selected.get(slot, "none") == row.get(slot, "none") for slot in DRAW_ORDER):
                return row["preset_id"]
        return None

    def cycle(self, selected: dict[str, str], slot: str, step: int) -> tuple[dict[str, str], str]:
        values = self.choices_by_slot.get(slot, [])
        if not values:
            return selected, f"No choices for {slot}"
        current = selected.get(slot, "none")
        try:
            start = values.index(current)
        except ValueError:
            start = 0
        for offset in range(1, len(values) + 1):
            candidate = dict(selected)
            candidate[slot] = values[(start + step * offset) % len(values)]
            valid, reason = self.validate(candidate)
            if valid:
                return candidate, f"{SLOT_LABELS.get(slot, slot)}: {candidate[slot]}"
        return selected, f"No compatible {slot} choice"

    def _image(self, relative: str):
        if relative not in self._images:
            self._images[relative] = self.pg.image.load(str(self.root / relative)).convert_alpha()
        return self._images[relative]

    def modular_frame(self, mode: str, selected: dict[str, str], row: int, direction: int):
        valid, reason = self.validate(selected)
        if not valid:
            raise PackError(reason)
        surface = self.pg.Surface((CELL, CELL), self.pg.SRCALPHA)
        source = self.pg.Rect(direction * CELL, row * CELL, CELL, CELL)
        for slot in DRAW_ORDER:
            part_id = selected.get(slot, "none")
            key = (mode, slot, part_id)
            if part_id != "none" and key in self.parts:
                surface.blit(self._image(self.parts[key]), (0, 0), source)
        return surface

    def fluid_frame(self, mode: str, selected: dict[str, str], animation: str, frame_index: int, direction: int):
        profile = self.matching_profile(selected)
        if profile is None:
            return None
        record = self.fluid.get((mode, profile, animation))
        if record is None:
            return None
        count = int(record["frame_count"])
        sheet = self._image(record["sheet"])
        source = self.pg.Rect((frame_index % count) * CELL, direction * CELL, CELL, CELL)
        result = self.pg.Surface((CELL, CELL), self.pg.SRCALPHA)
        result.blit(sheet, (0, 0), source)
        return result

    def wide_gait_fallback(self, frame, mode: str, frame_index: int):
        """Widen the lower-body stance for custom mixes without a fluid run sheet."""
        bounds = frame.get_bounding_rect(min_alpha=1)
        if bounds.width < 2 or bounds.height < 4:
            return frame
        amplitude = (1.02, 1.10, 1.26, 1.10, 1.02, 1.10, 1.26, 1.10)[frame_index % 8]
        if mode == "topdown":
            amplitude = 1.0 + (amplitude - 1.0) * 0.55
            split_y = bounds.top + int(bounds.height * 0.72)
        else:
            split_y = bounds.top + int(bounds.height * 0.55)
        split_y = max(bounds.top + 1, min(bounds.bottom - 1, split_y))
        lower_rect = self.pg.Rect(bounds.left, split_y, bounds.width, bounds.bottom - split_y)
        lower = frame.subsurface(lower_rect).copy()
        wider_w = max(lower.get_width(), int(round(lower.get_width() * amplitude)))
        wider = self.pg.transform.smoothscale(lower, (wider_w, lower.get_height()))
        result = frame.copy()
        result.fill((0, 0, 0, 0), lower_rect.inflate(max(0, wider_w - lower_rect.width), 0))
        result.blit(wider, wider.get_rect(midtop=(lower_rect.centerx, lower_rect.top)))
        return result

    def automatic_idle_frame(self, mode: str, selected: dict[str, str], animation: str, frame_index: int, direction: int):
        """Return authored preset idle art, with a registered modular fallback."""
        fluid = self.fluid_frame(mode, selected, animation, frame_index, direction)
        if fluid is not None:
            return fluid, "authored"
        base = self.modular_frame(mode, selected, 0, direction)
        bounds = base.get_bounding_rect(min_alpha=1)
        if not bounds.width or not bounds.height:
            return base, "modular"
        if animation == "waiting_12":
            width_delta = height_delta = 0
            shift_x = (0, 0, 0, 1, 2, 2, 1, 0, -1, -1, 0, 0)[frame_index % 12]
            shift_y = (0, 0, 0, 0, -1, -1, 0, 0, 0, 0, 0, 0)[frame_index % 12]
        else:
            width_delta = (0, 1, 2, 1, 0, -1)[frame_index % 6]
            height_delta = (0, 0, 1, 1, 0, 0)[frame_index % 6]
            shift_x = shift_y = 0
        split_ratio = 0.80 if mode == "topdown" else 0.70
        split_y = bounds.top + max(2, round(bounds.height * split_ratio))
        upper_rect = self.pg.Rect(bounds.left, bounds.top, bounds.width, max(2, split_y - bounds.top + 1))
        upper = base.subsurface(upper_rect).copy()
        scaled = self.pg.transform.scale(
            upper,
            (max(1, upper.get_width() + width_delta), max(1, upper.get_height() + height_delta)),
        )
        result = base.copy()
        result.fill((0, 0, 0, 0), upper_rect)
        target = scaled.get_rect(midbottom=(upper_rect.centerx + shift_x, upper_rect.bottom + shift_y))
        result.blit(scaled, target)
        return result, "modular"

    def action_frame(self, mode: str, action: str, row: int, direction: int):
        relative = self.actions[(mode, action)]
        sheet = self._image(relative)
        result = self.pg.Surface((CELL, CELL), self.pg.SRCALPHA)
        result.blit(sheet, (0, 0), self.pg.Rect(direction * CELL, row * CELL, CELL, CELL))
        return result

    @staticmethod
    def depth_sort_key(mode: str, world_x: float, ground_y: float, stable_id: int = 0):
        if mode == "topdown":
            return ground_y, world_x, stable_id
        return world_x + ground_y, ground_y, stable_id


class Button:
    def __init__(self, pygame_module, rect, label: str, kind: str, value: str = ""):
        self.pg = pygame_module
        self.rect = self.pg.Rect(rect)
        self.label = label
        self.kind = kind
        self.value = value

    def draw(self, screen, font, mouse_pos, active=False):
        hover = self.rect.collidepoint(mouse_pos)
        color = (49, 88, 94) if active else ((57, 64, 67) if hover else (43, 49, 51))
        self.pg.draw.rect(screen, color, self.rect, border_radius=5)
        self.pg.draw.rect(screen, (108, 135, 137), self.rect, 1, border_radius=5)
        text = font.render(self.label, True, (236, 232, 213))
        screen.blit(text, text.get_rect(center=self.rect.center))


class SpriteTester:
    def __init__(self, pygame_module, screen, pack: SpritePack, pack_argument: str):
        self.pg = pygame_module
        self.screen = screen
        self.pack = pack
        self.pack_argument = pack_argument
        self.clock = self.pg.time.Clock()
        self.font = self.pg.font.Font(None, 22)
        self.small = self.pg.font.Font(None, 18)
        self.title_font = self.pg.font.Font(None, 31)
        self.mode = "topdown"
        self.camera_angle = 0.0
        self.camera_dragging = False
        self.camera_drag_sensitivity = math.radians(float(pack.camera_settings.get("drag_sensitivity_degrees_per_pixel", 0.35)))
        self.position = self.pg.Vector2(WORLD_SIZE[0] / 2, WORLD_SIZE[1] / 2)
        self.world_heading = self.pg.Vector2(0, -1)
        self.aim_world = self.pg.Vector2(0, -1)
        self.direction = 0
        self.selected = pack.preset(0)
        self.preset_index = 0
        self.sprite_scale = 1.35
        self.camera_zoom = float(pack.camera_settings.get("zoom_default", 1.0))
        self.camera_zoom_min = float(pack.camera_settings.get("zoom_min", 0.55))
        self.camera_zoom_max = float(pack.camera_settings.get("zoom_max", 2.0))
        self.camera_zoom_step = float(pack.camera_settings.get("zoom_step", 0.10))
        self.camera_zoom = max(self.camera_zoom_min, min(self.camera_zoom_max, self.camera_zoom))
        self.animation_time = 0.0
        self.idle_time = 0.0
        self.slow_walking = False
        self.sprinting = False
        self.sprint_active = False
        self.sprint_trigger_key: int | None = None
        self.last_direction_tap: dict[int, float] = {}
        self.one_shot: str | None = None
        self.one_shot_time = 0.0
        self.jump_velocity = self.pg.Vector2()
        self.jump_distance = 0.0
        self.prone = False
        self.stand_delay_remaining = 0.0
        self.crouch_cancel_latched = False
        self.gun_row = 1
        open_assets = Path(__file__).resolve().parent / "assets" / "open_source_import"
        self.open_asset_car = None
        self.open_asset_buildings: dict[str, object] = {}
        self.sprint_dust_atlas = None
        try:
            self.open_asset_car = self.pg.image.load(str(open_assets / "vehicles" / "arcade_car_01_topdown.png")).convert_alpha()
            for camera_mode in ("topdown", "isometric"):
                self.open_asset_buildings[camera_mode] = self.pg.image.load(str(open_assets / "city" / f"city_building_01_{camera_mode}.png")).convert_alpha()
            self.sprint_dust_atlas = self.pg.image.load(str(open_assets / "effects" / "sprint_dust_8.png")).convert_alpha()
        except (self.pg.error, OSError):
            self.open_asset_car = None
            self.open_asset_buildings = {}
            self.sprint_dust_atlas = None
        self.status = "Pack loaded. Customize on the right, then use WASD."
        self.status_until = time.monotonic() + 6.0
        self.last_move_time = 0.0
        self.buttons: list[Button] = []
        self.slot_buttons: list[Button] = []
        self._build_buttons()

    def _build_buttons(self) -> None:
        pg = self.pg
        self.buttons = [
            Button(pg, (900, 68, 165, 34), "Top-down / Isometric", "toggle_mode"),
            Button(pg, (1074, 68, 82, 34), "Rotate -", "camera", "-1"),
            Button(pg, (1164, 68, 82, 34), "Rotate +", "camera", "1"),
            Button(pg, (900, 108, 165, 31), "Previous preset", "preset", "-1"),
            Button(pg, (1074, 108, 172, 31), "Next preset", "preset", "1"),
            Button(pg, (900, 494, 108, 32), "Jump", "action", "jump"),
            Button(pg, (1017, 494, 108, 32), "Turn", "action", "turn"),
            Button(pg, (1134, 494, 112, 32), "Punch", "action", "punch"),
            Button(pg, (900, 534, 108, 32), "Prone", "action", "prone"),
            Button(pg, (1017, 534, 108, 32), "Gun hold", "action", "gun_hold"),
            Button(pg, (1134, 534, 112, 32), "Screenshot", "screenshot"),
            Button(pg, (900, 574, 165, 32), "Open sprite ZIP", "open_zip"),
            Button(pg, (1074, 574, 172, 32), "Open extracted folder", "open_folder"),
        ]
        self.slot_buttons = []
        y = 174
        for slot in ("body", "head", "top", "bottom", "footwear", "accessory"):
            self.slot_buttons.append(Button(pg, (900, y, 34, 32), "<", "cycle", f"{slot}:-1"))
            self.slot_buttons.append(Button(pg, (1212, y, 34, 32), ">", "cycle", f"{slot}:1"))
            y += 48

    def set_status(self, text: str, seconds: float = 3.0) -> None:
        self.status = text
        self.status_until = time.monotonic() + seconds

    def apply_preset(self, step: int) -> None:
        self.preset_index = (self.preset_index + step) % len(self.pack.presets)
        self.selected = self.pack.preset(self.preset_index)
        self.idle_time = 0.0
        self.set_status(f"Preset: {self.pack.preset_name(self.preset_index)}")

    def cancel_sprint(self) -> None:
        self.sprinting = False
        self.sprint_active = False
        self.sprint_trigger_key = None

    def register_direction_tap(self, key: int, now: float | None = None) -> bool:
        """Arm sprint when the same direction is pressed twice inside the configured window."""
        direction_keys = (self.pg.K_w, self.pg.K_a, self.pg.K_s, self.pg.K_d)
        if key not in direction_keys:
            return False
        timestamp = time.monotonic() if now is None else now
        keys = self.pg.key.get_pressed()
        blocked = (
            self.prone
            or self.one_shot is not None
            or bool(keys[self.pg.K_c])
            or bool(keys[self.pg.K_LSHIFT] or keys[self.pg.K_RSHIFT])
        )
        if blocked:
            self.last_direction_tap.pop(key, None)
            return False
        previous = self.last_direction_tap.get(key)
        self.last_direction_tap[key] = timestamp
        window = float(self.pack.movement_settings.get("sprint_double_tap_window_seconds", 0.30))
        if previous is not None and 0.0 <= timestamp - previous <= window:
            self.sprinting = True
            self.sprint_trigger_key = key
            self.last_direction_tap.pop(key, None)
            self.idle_time = 0.0
            self.set_status("RUNNING 3×: release the twice-tapped direction to stop")
            return True
        return False

    def trigger(self, action: str) -> None:
        self.cancel_sprint()
        self.idle_time = 0.0
        if action == "prone":
            if self.one_shot in {"jump", "double_jump"}:
                self.set_status("Cannot change prone state while airborne")
                return
            self.prone = not self.prone
            self.stand_delay_remaining = 0.0
            self.one_shot = None
            self.set_status("Prone" if self.prone else "Standing")
            return
        if action == "jump":
            if self.prone:
                self.prone = False
                self.stand_delay_remaining = 0.0
                self.one_shot = None
                self.set_status("Standing up with jump control")
                return
            double_window = float(self.pack.movement_settings.get("double_jump_window_seconds", 0.55))
            if self.one_shot == "jump" and self.one_shot_time <= double_window:
                self.one_shot = "double_jump"
                self.one_shot_time = 0.0
                forward = self.world_heading.normalize() if self.world_heading.length_squared() else self.screen_to_world_delta(self.pg.Vector2(0, -1))
                self.jump_velocity = forward * float(self.pack.movement_settings.get("double_jump_forward_speed_px_per_second", 470.0))
                self.set_status("DOUBLE JUMP: stronger forward burst; landing prone")
                return
            if self.one_shot in {"jump", "double_jump"}:
                return
            forward = self.world_heading.normalize() if time.monotonic() - self.last_move_time < 0.8 else self.screen_to_world_delta(self.pg.Vector2(0, -1))
            self.world_heading = forward
            self.jump_velocity = forward * float(self.pack.movement_settings.get("jump_forward_speed_px_per_second", 285.0))
            self.jump_distance = 0.0
            self.one_shot = "jump"
            self.one_shot_time = 0.0
            self.direction = self.direction_from_vector(self.world_to_screen_delta(forward))
            self.set_status("Forward jump: press Space again while airborne for double jump")
            return
        if action == "gun_hold":
            self.gun_row = (self.gun_row + 1) % 4
            self.one_shot = "gun_hold"
            self.one_shot_time = 0.0
            labels = ("one hand", "compact two hand", "long low", "long aimed")
            self.set_status(f"Gun-hold master: {labels[self.gun_row]}")
            return
        self.prone = False
        self.stand_delay_remaining = 0.0
        self.one_shot = action
        self.one_shot_time = 0.0
        self.set_status(action.replace("_", " ").title())

    def choose_path(self, folder: bool) -> Path | None:
        try:
            import tkinter as tk
            from tkinter import filedialog

            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            if folder:
                chosen = filedialog.askdirectory(title="Choose extracted dual-camera sprite pack")
            else:
                chosen = filedialog.askopenfilename(title="Choose sprite-pack ZIP", filetypes=[("ZIP files", "*.zip")])
            root.destroy()
            return Path(chosen) if chosen else None
        except Exception as exc:
            self.set_status(f"File dialog unavailable: {exc}", 6.0)
            return None

    def replace_pack(self, path: Path) -> None:
        old = self.pack
        source: LoadedSource | None = None
        try:
            source = load_source(path)
            new_pack = SpritePack(self.pg, source)
        except Exception as exc:
            if source is not None:
                source.close()
            self.set_status(f"Could not load pack: {exc}", 8.0)
            return
        self.pack = new_pack
        self.pack_argument = str(path)
        old.close()
        self.camera_drag_sensitivity = math.radians(float(new_pack.camera_settings.get("drag_sensitivity_degrees_per_pixel", 0.35)))
        self.camera_zoom_min = float(new_pack.camera_settings.get("zoom_min", 0.55))
        self.camera_zoom_max = float(new_pack.camera_settings.get("zoom_max", 2.0))
        self.camera_zoom_step = float(new_pack.camera_settings.get("zoom_step", 0.10))
        self.camera_zoom = max(self.camera_zoom_min, min(self.camera_zoom_max, self.camera_zoom))
        self.preset_index = 0
        self.selected = new_pack.preset(0)
        self.idle_time = 0.0
        self.cancel_sprint()
        self.last_direction_tap.clear()
        self.set_status(f"Loaded: {path.name}", 5.0)

    def screenshot(self) -> Path:
        folder = Path(__file__).resolve().parent / "screenshots"
        folder.mkdir(exist_ok=True)
        path = folder / time.strftime("sprite_test_%Y%m%d_%H%M%S.png")
        self.pg.image.save(self.screen, str(path))
        self.set_status(f"Saved {path.name}")
        return path

    def handle_click(self, pos) -> None:
        for button in self.slot_buttons + self.buttons:
            if not button.rect.collidepoint(pos):
                continue
            if button.kind == "cycle":
                slot, step = button.value.split(":")
                self.selected, message = self.pack.cycle(self.selected, slot, int(step))
                self.idle_time = 0.0
                self.set_status(message)
            elif button.kind == "toggle_mode":
                self.mode = "isometric" if self.mode == "topdown" else "topdown"
                self.set_status(f"Camera mode: {self.mode}")
            elif button.kind == "camera":
                self.rotate_camera(math.radians(15 * int(button.value)))
            elif button.kind == "preset":
                self.apply_preset(int(button.value))
            elif button.kind == "action":
                self.trigger(button.value)
            elif button.kind == "screenshot":
                self.screenshot()
            elif button.kind in {"open_zip", "open_folder"}:
                path = self.choose_path(button.kind == "open_folder")
                if path:
                    self.replace_pack(path)
            return

    def handle_event(self, event) -> bool:
        if event.type == self.pg.QUIT:
            return False
        if event.type == self.pg.MOUSEBUTTONDOWN and event.button == 1:
            self.handle_click(event.pos)
        if event.type == self.pg.MOUSEBUTTONDOWN and event.button == 2 and self.pg.Rect(WORLD_RECT).collidepoint(event.pos):
            self.camera_dragging = True
            self.direction = 0
            self.set_status("Camera rotation: middle mouse drag; player front-locked")
        if event.type == self.pg.MOUSEBUTTONUP and event.button == 2:
            self.camera_dragging = False
        if event.type == self.pg.MOUSEMOTION and self.camera_dragging:
            self.rotate_camera(event.rel[0] * self.camera_drag_sensitivity, announce=False)
            self.direction = 0
        if event.type == self.pg.MOUSEWHEEL and self.pg.Rect(WORLD_RECT).collidepoint(self.pg.mouse.get_pos()):
            self.adjust_camera_zoom(event.y)
        if event.type == self.pg.KEYUP and event.key == self.sprint_trigger_key:
            self.cancel_sprint()
        if event.type == self.pg.KEYDOWN:
            if event.key in (self.pg.K_w, self.pg.K_a, self.pg.K_s, self.pg.K_d) and not getattr(event, "repeat", False):
                self.register_direction_tap(event.key)
            if event.key == self.pg.K_ESCAPE:
                return False
            if event.key == self.pg.K_TAB:
                self.mode = "isometric" if self.mode == "topdown" else "topdown"
                self.set_status(f"Camera mode: {self.mode}")
            elif event.key == self.pg.K_q:
                self.rotate_camera(math.radians(-15))
            elif event.key == self.pg.K_e:
                self.rotate_camera(math.radians(15))
            elif event.key == self.pg.K_SPACE:
                self.trigger("jump")
            elif event.key == self.pg.K_t:
                self.trigger("turn")
            elif event.key == self.pg.K_f:
                self.trigger("punch")
            elif event.key == self.pg.K_g:
                self.trigger("gun_hold")
            elif event.key == self.pg.K_x:
                self.trigger("prone")
            elif event.key == self.pg.K_F12:
                self.screenshot()
            elif self.pg.K_0 <= event.key <= self.pg.K_9:
                number = 9 if event.key == self.pg.K_0 else event.key - self.pg.K_1
                self.preset_index = number % len(self.pack.presets)
                self.selected = self.pack.preset(self.preset_index)
                self.idle_time = 0.0
                self.set_status(f"Preset: {self.pack.preset_name(self.preset_index)}")
            elif event.key in (self.pg.K_EQUALS, self.pg.K_KP_PLUS):
                self.adjust_camera_zoom(1)
            elif event.key in (self.pg.K_MINUS, getattr(self.pg, "K_KP_MINUS", self.pg.K_MINUS)):
                self.adjust_camera_zoom(-1)
        return True

    @staticmethod
    def direction_from_vector(vector) -> int:
        # Screen coordinates use +Y downward. Offset by two octants so east=2.
        return (round(math.atan2(vector.y, vector.x) / (math.pi / 4)) + 2) % 8

    def rotate_camera(self, delta_radians: float, announce: bool = True) -> None:
        self.camera_angle = (self.camera_angle + delta_radians) % math.tau
        if announce:
            self.set_status(f"Camera rotation: {math.degrees(self.camera_angle):.0f} degrees")

    def adjust_camera_zoom(self, wheel_y: int) -> None:
        if not wheel_y:
            return
        old = self.camera_zoom
        self.camera_zoom = max(
            self.camera_zoom_min,
            min(self.camera_zoom_max, old + float(wheel_y) * self.camera_zoom_step),
        )
        if abs(self.camera_zoom - old) > 1e-6:
            self.set_status(f"Camera zoom {self.camera_zoom:.2f}x")

    def screen_to_world_delta(self, vector):
        c, s = math.cos(self.camera_angle), math.sin(self.camera_angle)
        return self.pg.Vector2(c * vector.x - s * vector.y, s * vector.x + c * vector.y)

    def world_to_screen_delta(self, vector):
        c, s = math.cos(self.camera_angle), math.sin(self.camera_angle)
        return self.pg.Vector2(c * vector.x + s * vector.y, -s * vector.x + c * vector.y)

    def world_to_screen(self, world_position):
        left, top, width, height = WORLD_RECT
        center = self.pg.Vector2(left + width / 2, top + height / 2)
        delta = self.world_to_screen_delta(self.pg.Vector2(world_position) - self.position)
        return center + delta * self.camera_zoom

    def rotated_depth_key(self, world_position, stable_id: int):
        screen = self.world_to_screen(world_position)
        return screen.y, screen.x, stable_id

    def update(self, dt: float) -> tuple[bool, bool]:
        keys = self.pg.key.get_pressed()
        move = self.pg.Vector2(
            float(keys[self.pg.K_d]) - float(keys[self.pg.K_a]),
            float(keys[self.pg.K_s]) - float(keys[self.pg.K_w]),
        )
        moving = move.length_squared() > 0
        crouch_requested = bool(keys[self.pg.K_c])
        if not crouch_requested:
            self.crouch_cancel_latched = False
        crouching = crouch_requested and not self.crouch_cancel_latched
        slow_held = bool(keys[self.pg.K_LSHIFT] or keys[self.pg.K_RSHIFT])
        airborne = self.one_shot in {"jump", "double_jump"}
        sprint_blocked = slow_held or crouching or self.prone or airborne or self.one_shot is not None
        trigger_held = self.sprint_trigger_key is not None and bool(keys[self.sprint_trigger_key])
        if self.sprinting and (sprint_blocked or not moving or not trigger_held):
            self.cancel_sprint()
        self.sprint_active = self.sprinting and moving and trigger_held and not sprint_blocked
        if moving and not airborne and self.one_shot != "punch":
            if self.prone or crouching:
                delay = float(self.pack.movement_settings.get("movement_stand_delay_seconds", 1.0))
                if self.stand_delay_remaining <= 0.0:
                    self.stand_delay_remaining = delay
                    self.set_status(f"Standing up: movement resumes in {delay:.1f}s")
                self.stand_delay_remaining = max(0.0, self.stand_delay_remaining - dt)
                if self.stand_delay_remaining <= 0.0:
                    self.prone = False
                    self.crouch_cancel_latched = crouch_requested
                    crouching = False
                    self.set_status("Standing: movement resumed")
                else:
                    moving = False
            if moving:
                screen_move = move.normalize()
                world_move = self.screen_to_world_delta(screen_move)
                speed = float(self.pack.movement_settings.get("walk_speed_px_per_second", 185.0))
                if slow_held:
                    speed *= float(self.pack.movement_settings.get("slow_walk_multiplier", 0.55))
                elif self.sprint_active:
                    speed *= float(self.pack.movement_settings.get("sprint_speed_multiplier", 3.0))
                self.position += world_move * speed * dt
                self.world_heading = world_move
                self.direction = 0 if self.camera_dragging else self.direction_from_vector(screen_move)
                self.last_move_time = time.monotonic()
        elif airborne:
            self.stand_delay_remaining = 0.0
            displacement = self.jump_velocity * dt
            self.position += displacement
            self.jump_distance += displacement.length()
            self.jump_velocity *= max(0.0, 1.0 - dt * (0.85 if self.one_shot == "double_jump" else 1.15))
            if not self.camera_dragging:
                self.direction = self.direction_from_vector(self.world_to_screen_delta(self.world_heading))
        elif not moving and time.monotonic() - self.last_move_time > 0.6 and self.one_shot is None:
            self.stand_delay_remaining = 0.0
            # Current project rule: body returns to camera/screen-forward idle.
            self.direction = 0
        margin = 80
        self.position.x = max(margin, min(WORLD_SIZE[0] - margin, self.position.x))
        self.position.y = max(margin, min(WORLD_SIZE[1] - margin, self.position.y))
        left, top, width, height = WORLD_RECT
        actor_center = self.pg.Vector2(left + width / 2, top + height / 2)
        mouse_delta = self.pg.Vector2(self.pg.mouse.get_pos()) - actor_center
        if mouse_delta.length_squared() > 1:
            self.aim_world = self.screen_to_world_delta(mouse_delta.normalize())
        self.slow_walking = moving and not airborne and slow_held
        if self.sprint_active:
            animation_rate = float(self.pack.movement_settings.get("sprint_animation_rate_multiplier", 1.85))
        elif self.slow_walking:
            animation_rate = float(self.pack.movement_settings.get("slow_walk_multiplier", 0.55))
        else:
            animation_rate = 1.0
        self.animation_time += dt * animation_rate
        if self.one_shot is not None:
            self.one_shot_time += dt
            durations = {
                "jump": float(self.pack.movement_settings.get("jump_duration_seconds", 0.75)),
                "double_jump": float(self.pack.movement_settings.get("double_jump_duration_seconds", 0.95)),
                "turn": 0.42, "punch": 0.42, "gun_hold": 0.9,
            }
            if self.one_shot_time >= durations.get(self.one_shot, 0.5):
                landed_from_double = self.one_shot == "double_jump"
                self.one_shot = None
                self.one_shot_time = 0.0
                self.jump_velocity.update(0, 0)
                if landed_from_double:
                    self.prone = True
                    self.set_status(f"Landed prone after {self.jump_distance:.0f}px: Space or X stands up", 5.0)
        automatic_idle = not moving and not crouching and not self.prone and self.one_shot is None and self.stand_delay_remaining <= 0.0
        self.idle_time = self.idle_time + dt if automatic_idle else 0.0
        return moving, crouching

    def current_frame(self, moving: bool, crouching: bool):
        if self.one_shot == "punch":
            row = min(3, int(self.one_shot_time * 10))
            return self.pack.action_frame(self.mode, "punch", row, self.direction), "punch master"
        if self.one_shot == "gun_hold":
            return self.pack.action_frame(self.mode, "gun_hold", self.gun_row, self.direction), "gun-hold master"
        if self.one_shot in {"jump", "double_jump"}:
            if self.one_shot == "double_jump":
                rows = (5, 5, 6, 6, 7)
                index = min(len(rows) - 1, int(self.one_shot_time * 6))
                return self.pack.modular_frame(self.mode, self.selected, rows[index], self.direction), "double jump → prone"
            rows = (0, 6, 5, 6, 0)
            index = min(len(rows) - 1, int(self.one_shot_time * 8))
            return self.pack.modular_frame(self.mode, self.selected, rows[index], self.direction), "modular jump"
        if self.one_shot == "turn":
            rows = (0, 4, 0)
            index = min(len(rows) - 1, int(self.one_shot_time * 10))
            return self.pack.modular_frame(self.mode, self.selected, rows[index], self.direction), "modular turn"
        if self.prone:
            return self.pack.modular_frame(self.mode, self.selected, 7, self.direction), "modular prone"
        if crouching:
            return self.pack.modular_frame(self.mode, self.selected, 6, self.direction), "modular crouch"
        if moving:
            fluid_index = int(self.animation_time * 12) % 8
            gait = "run_wide_8" if self.sprint_active else "walk_8"
            fluid = self.pack.fluid_frame(self.mode, self.selected, gait, fluid_index, self.direction)
            if fluid is not None:
                return fluid, "fluid preset wide-gait run" if self.sprint_active else "fluid preset walk"
            rows = (1, 2, 3, 2)
            row = rows[int(self.animation_time * 8) % len(rows)]
            modular = self.pack.modular_frame(self.mode, self.selected, row, self.direction)
            if self.sprint_active:
                modular = self.pack.wide_gait_fallback(modular, self.mode, fluid_index)
                return modular, "modular wide-gait run"
            return modular, "modular walk"
        breathing_start = float(self.pack.idle_settings.get("breathing_start_seconds", 0.35))
        waiting_start = float(self.pack.idle_settings.get("waiting_start_seconds", 6.0))
        waiting_interval = float(self.pack.idle_settings.get("waiting_interval_seconds", 10.0))
        waiting_duration = float(self.pack.idle_settings.get("waiting_duration_seconds", 3.0))
        if self.idle_time >= waiting_start:
            waiting_phase = (self.idle_time - waiting_start) % max(waiting_duration, waiting_interval)
            if waiting_phase < waiting_duration:
                fps = float(self.pack.idle_settings.get("waiting_fps", 4.0))
                frame_index = int(waiting_phase * fps) % 12
                frame, source = self.pack.automatic_idle_frame(self.mode, self.selected, "waiting_12", frame_index, self.direction)
                return frame, f"{source} automatic waiting"
        if self.idle_time >= breathing_start:
            fps = float(self.pack.idle_settings.get("breathing_fps", 3.0))
            frame_index = int((self.idle_time - breathing_start) * fps) % 6
            frame, source = self.pack.automatic_idle_frame(self.mode, self.selected, "breathing_6", frame_index, self.direction)
            return frame, f"{source} automatic breathing"
        return self.pack.modular_frame(self.mode, self.selected, 0, self.direction), "modular idle"

    def draw_world(self, moving: bool, crouching: bool) -> str:
        pg = self.pg
        left, top, width, height = WORLD_RECT
        world_rect = pg.Rect(WORLD_RECT)
        previous_clip = self.screen.get_clip()
        self.screen.set_clip(world_rect)
        pg.draw.rect(self.screen, (42, 49, 48), world_rect)

        # Rotate all world geometry around the player, who stays screen-centered.
        tile = 128
        visible_radius = 1100 / max(0.05, self.camera_zoom)
        min_x = max(0, int((self.position.x - visible_radius) // tile) * tile)
        max_x = min(WORLD_SIZE[0], int((self.position.x + visible_radius) // tile + 1) * tile)
        min_y = max(0, int((self.position.y - visible_radius) // tile) * tile)
        max_y = min(WORLD_SIZE[1], int((self.position.y + visible_radius) // tile + 1) * tile)
        for world_x in range(min_x, max_x + 1, tile):
            a = self.world_to_screen((world_x, min_y))
            b = self.world_to_screen((world_x, max_y))
            pg.draw.line(self.screen, (56, 65, 63), a, b, 1)
        for world_y in range(min_y, max_y + 1, tile):
            a = self.world_to_screen((min_x, world_y))
            b = self.world_to_screen((max_x, world_y))
            pg.draw.line(self.screen, (56, 65, 63), a, b, 1)

        road_y = WORLD_SIZE[1] / 2
        road = [
            self.world_to_screen((0, road_y - 92)), self.world_to_screen((WORLD_SIZE[0], road_y - 92)),
            self.world_to_screen((WORLD_SIZE[0], road_y + 92)), self.world_to_screen((0, road_y + 92)),
        ]
        pg.draw.polygon(self.screen, (57, 61, 61), road)
        pg.draw.line(self.screen, (193, 164, 72), self.world_to_screen((0, road_y)), self.world_to_screen((WORLD_SIZE[0], road_y)), max(1, round(4 * self.camera_zoom)))
        for world_x in range(0, WORLD_SIZE[0], 130):
            pg.draw.line(
                self.screen, (226, 216, 164),
                self.world_to_screen((world_x, road_y)), self.world_to_screen((world_x + 55, road_y)), max(1, round(3 * self.camera_zoom)),
            )

        sprite, source_label = self.current_frame(moving, crouching)
        target_size = max(1, int(CELL * self.sprite_scale * self.camera_zoom))
        sprite = pg.transform.smoothscale(sprite, (target_size, target_size))
        actor_center = pg.Vector2(left + width / 2, top + height / 2)
        sprite_rect = sprite.get_rect(center=actor_center)

        tree_world = pg.Vector2(WORLD_SIZE[0] / 2 - 260, WORLD_SIZE[1] / 2 - 165)
        planter_world = pg.Vector2(WORLD_SIZE[0] / 2 + 310, WORLD_SIZE[1] / 2 + 225)
        imported_building_world = pg.Vector2(WORLD_SIZE[0] / 2 + 245, WORLD_SIZE[1] / 2 - 220)
        renderables = [
            (self.rotated_depth_key(tree_world, 1), "tree", tree_world),
            (self.rotated_depth_key(self.position, 2), "actor", self.position),
            (self.rotated_depth_key(planter_world, 3), "asset_car", planter_world),
            (self.rotated_depth_key(imported_building_world, 4), "asset_building", imported_building_world),
        ]
        for _key, kind, world_position in sorted(renderables, key=lambda item: item[0]):
            anchor = self.world_to_screen(world_position)
            z = self.camera_zoom
            if kind == "actor":
                if self.sprint_active and self.sprint_dust_atlas is not None:
                    dust_cell = 64
                    dust_index = int(self.animation_time * 18.0) % 8
                    dust = self.sprint_dust_atlas.subsurface(pg.Rect(dust_index * dust_cell, 0, dust_cell, dust_cell)).copy()
                    dust_size = max(18, int(48 * z))
                    dust = pg.transform.smoothscale(dust, (dust_size, dust_size))
                    self.screen.blit(dust, dust.get_rect(midbottom=(actor_center.x, actor_center.y + 31 * z)))
                self.screen.blit(sprite, sprite_rect)
            elif kind == "tree":
                x, ground_y = anchor
                pg.draw.ellipse(self.screen, (25, 31, 28), (x - 58*z, ground_y - 24*z, 116*z, 35*z))
                pg.draw.rect(self.screen, (83, 60, 37), (x - 9*z, ground_y - 75*z, 18*z, 65*z), border_radius=max(1, round(5*z)))
                for dx, dy, radius in ((-30, -100, 42), (25, -104, 45), (0, -136, 50)):
                    pg.draw.circle(self.screen, (61, 100, 61), (x + dx*z, ground_y + dy*z), max(1, round(radius*z)))
                    pg.draw.circle(self.screen, (99, 137, 73), (x + (dx - 8)*z, ground_y + (dy - 7)*z), max(2, round((radius - 12)*z)), max(1, round(3*z)))
            elif kind == "asset_car" and self.open_asset_car is not None:
                car = pg.transform.rotozoom(self.open_asset_car, math.degrees(self.camera_angle), max(0.12, 0.46 * z))
                self.screen.blit(car, car.get_rect(center=anchor))
            elif kind == "asset_building" and self.mode in self.open_asset_buildings:
                source = self.open_asset_buildings[self.mode]
                target_height = max(34, int(148 * z))
                target_width = max(24, round(source.get_width() * target_height / max(1, source.get_height())))
                building = pg.transform.smoothscale(source, (target_width, target_height))
                self.screen.blit(building, building.get_rect(midbottom=anchor))

        # North-up minimap: camera rotation changes the view cone, never map north.
        mini = pg.Rect(left + 14, top + 14, 154, 116)
        pg.draw.rect(self.screen, (20, 25, 25), mini, border_radius=5)
        pg.draw.rect(self.screen, (102, 126, 126), mini, 1, border_radius=5)
        map_scale = min((mini.width - 12) / WORLD_SIZE[0], (mini.height - 12) / WORLD_SIZE[1])
        player_mini = pg.Vector2(mini.x + self.position.x * map_scale, mini.y + self.position.y * map_scale)
        for position, color in ((tree_world, (76, 130, 76)), (planter_world, (95, 165, 205)), (imported_building_world, (146, 139, 126))):
            point = pg.Vector2(mini.x + position.x * map_scale, mini.y + position.y * map_scale)
            pg.draw.circle(self.screen, color, point, 4)
        pg.draw.circle(self.screen, (112, 213, 225), player_mini, 5)
        camera_up = self.screen_to_world_delta(pg.Vector2(0, -1))
        pg.draw.line(self.screen, (112, 213, 225), player_mini, player_mini + camera_up * 17, 2)
        north = self.small.render("N", True, (235, 230, 208))
        self.screen.blit(north, north.get_rect(midtop=(mini.centerx, mini.y + 4)))
        angle_text = self.small.render(f"CAM {math.degrees(self.camera_angle):03.0f}°", True, (146, 194, 199))
        self.screen.blit(angle_text, (mini.x + 6, mini.bottom - 19))

        mouse = pg.Vector2(pg.mouse.get_pos())
        delta = mouse - actor_center
        if delta.length_squared() > 1:
            delta.scale_to_length(31)
            start = actor_center + pg.Vector2(0, -45)
            pg.draw.line(self.screen, (105, 210, 222), start, start + delta, 2)
            pg.draw.circle(self.screen, (105, 210, 222), start + delta, 3)
        self.screen.set_clip(previous_clip)
        return source_label

    def draw_panel(self, source_label: str, mouse_pos) -> None:
        pg = self.pg
        pg.draw.rect(self.screen, (29, 34, 35), (880, 0, 400, 760))
        pg.draw.line(self.screen, (82, 99, 100), (880, 0), (880, 760), 2)
        title = self.title_font.render("OPEN NIGHT MOVEMENT", True, (242, 235, 211))
        self.screen.blit(title, (900, 20))
        drag_label = " | ROTATING" if self.camera_dragging else ""
        sprint_label = " | RUN 3×" if self.sprint_active else ""
        info = self.small.render(f"{self.mode.upper()} | {math.degrees(self.camera_angle):.0f}° | {self.camera_zoom:.2f}x | facing {DIRECTIONS[self.direction]}{drag_label}{sprint_label}", True, (124, 201, 211))
        self.screen.blit(info, (900, 48))
        for button in self.buttons:
            if button.kind == "action" and button.value == "prone":
                button.label = "Stand up" if self.prone else "Prone"
            elif button.kind == "action" and button.value == "jump":
                button.label = "Stand up" if self.prone else ("Double jump" if self.one_shot == "jump" else "Jump")
            active = (
                (button.kind == "toggle_mode" and self.mode == "topdown")
                or (button.kind == "action" and self.one_shot == button.value)
                or (button.kind == "action" and button.value == "prone" and self.prone)
            )
            button.draw(self.screen, self.small, mouse_pos, active)

        y = 154
        for slot in ("body", "head", "top", "bottom", "footwear", "accessory"):
            label = self.small.render(SLOT_LABELS[slot], True, (166, 181, 177))
            value = self.font.render(self.selected.get(slot, "none"), True, (240, 235, 214))
            self.screen.blit(label, (944, y))
            self.screen.blit(value, value.get_rect(center=(1073, y + 36)))
            y += 48
        for button in self.slot_buttons:
            button.draw(self.screen, self.font, mouse_pos)

        preset = self.pack.matching_preset(self.selected)
        valid, reason = self.pack.validate(self.selected)
        status_color = (126, 207, 142) if valid else (228, 119, 102)
        pg.draw.rect(self.screen, (24, 28, 29), (900, 616, 346, 122), border_radius=6)
        self.screen.blit(self.small.render(f"Preset match: {preset or 'custom combination'}", True, (221, 205, 137)), (914, 628))
        self.screen.blit(self.small.render(reason, True, status_color), (914, 649))
        controls = (
            "Double-tap W/A/S/D = 3× run | Shift = slow walk",
            "WASD stands after 1s from crouch/prone",
            "Space jump | Space twice = 2×-range double jump",
            "Space/X stand | Middle drag rotate | Wheel zoom",
        )
        for index, line in enumerate(controls):
            self.screen.blit(self.small.render(line, True, (180, 188, 184)), (914, 674 + index * 15))
        if time.monotonic() < self.status_until:
            text = self.small.render(self.status, True, (250, 229, 141))
            self.screen.blit(text, (24, 724))

    def draw(self, moving: bool, crouching: bool) -> None:
        self.screen.fill((17, 21, 22))
        source_label = self.draw_world(moving, crouching)
        self.draw_panel(source_label, self.pg.mouse.get_pos())
        self.pg.display.flip()

    def run(self) -> None:
        running = True
        while running:
            dt = min(self.clock.tick(60) / 1000.0, 0.05)
            for event in self.pg.event.get():
                running = self.handle_event(event) and running
            moving, crouching = self.update(dt)
            self.draw(moving, crouching)


def locate_pack(argument: str | None, app_dir: Path) -> Path:
    if argument:
        return Path(argument)
    for candidate in default_pack_candidates(app_dir):
        if candidate.exists():
            return candidate
    raise PackError(
        "No sprite pack found. Put dual_camera_character_customization_set.zip "
        "next to the tester, or pass its path: python sprite_tester.py PACK.zip"
    )


def headless_smoke_test(pg, pack: SpritePack, output: Path) -> None:
    screen = pg.display.set_mode(WINDOW_SIZE)
    app = SpriteTester(pg, screen, pack, str(pack.root))
    app.selected = pack.preset(0)
    app.position = pg.Vector2(WORLD_SIZE[0] / 2, WORLD_SIZE[1] / 2)
    app.camera_angle = math.radians(32)
    app.direction = 1  # Show the northeast diagonal contract in the QA preview.
    app.animation_time = 2 / 12  # Peak wide-gait run frame.
    app.sprinting = True
    app.sprint_active = True
    app.draw(moving=True, crouching=False)
    output.parent.mkdir(parents=True, exist_ok=True)
    pg.image.save(screen, str(output))


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=APP_NAME)
    parser.add_argument("pack", nargs="?", help="Path to the sprite-pack ZIP or extracted folder")
    parser.add_argument("--headless-test", action="store_true", help="Render one frame and exit")
    parser.add_argument("--test-output", default="sprite_tester_smoke.png", help="Headless-test screenshot path")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    if args.headless_test:
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    try:
        import pygame
    except ImportError:
        print("Pygame is required. Run START_SPRITE_TESTER.bat or: python -m pip install pygame-ce", file=sys.stderr)
        return 2
    pygame.init()
    pygame.display.set_caption(APP_NAME)
    app_dir = Path(__file__).resolve().parent
    pack: SpritePack | None = None
    try:
        pack_path = locate_pack(args.pack, app_dir)
        pack = SpritePack(pygame, load_source(pack_path))
        if args.headless_test:
            headless_smoke_test(pygame, pack, Path(args.test_output).resolve())
            print(f"Headless sprite test passed: {Path(args.test_output).resolve()}")
            return 0
        screen = pygame.display.set_mode(WINDOW_SIZE, pygame.RESIZABLE)
        SpriteTester(pygame, screen, pack, str(pack_path)).run()
        return 0
    except Exception as exc:
        print(f"{APP_NAME}: {exc}", file=sys.stderr)
        return 1
    finally:
        if pack is not None:
            pack.close()
        pygame.quit()


if __name__ == "__main__":
    raise SystemExit(main())
