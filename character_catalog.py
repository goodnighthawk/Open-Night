from __future__ import annotations

import csv
import os
from functools import lru_cache
from pathlib import Path

from portable_paths import APP_DIR

BUNDLED_ROOT = APP_DIR / "assets" / "characters" / "master_dual_camera"
CHARACTER_PACK_ENV = "PYMMO_CHARACTER_PACK"

LEGACY_KEYS = ("skin_tone", "hair_style", "hair_color", "top_color", "pants_color")
PART_SLOTS = ("body", "head", "top", "bottom", "footwear", "accessory")
CUSTOM_SLOTS = ("head", "top", "bottom", "footwear", "accessory")
DUAL_CAMERA_MODES = ("topdown", "isometric")

DEFAULT_PROFILE = "street_blue"
LEGACY_PROFILE_ORDER = (
    "street_blue",
    "cap_red",
    "masked_olive",
    "rider",
)

# The newest pack keeps fluid composites under historical profile IDs while the
# public customization catalog uses cleaner preset IDs. These five mappings are
# exact part-for-part matches in the shipped preset table.
PRESET_TO_FLUID_PROFILE = {
    "street_blue": "tshirt_blue_curly",
    "masked_olive": "hoodie_olive_fade_mask",
    "night_jacket": "jacket_black_ponytail_shades",
    "cap_red": "tshirt_red_cap_shorts",
    "rider": "rider_fullface",
}


def pack_root() -> Path:
    # Release builds are self-contained.  An older pack under the shared-data
    # folder can have compatible CSV names but different PNG grids; silently
    # preferring it made a freshly unzipped client crash while drawing cyclists.
    # Modders can still opt into a complete external pack explicitly.
    raw = os.getenv(CHARACTER_PACK_ENV, "").strip()
    if raw:
        candidate = Path(raw).expanduser().resolve()
        required = (
            candidate / "config" / "paired_parts.csv",
            candidate / "config" / "fluid_animations.csv",
        )
        if all(path.is_file() for path in required):
            return candidate
    return BUNDLED_ROOT


def _rows(name: str) -> list[dict[str, str]]:
    path = pack_root() / "config" / name
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _truthy(value: object, default: bool = False) -> bool:
    text = str(value or "").strip().lower()
    if not text:
        return default
    return text in {"1", "true", "yes", "y", "on"}


@lru_cache(maxsize=1)
def catalog() -> dict:
    parts_by_mode: dict[str, dict[str, list[str]]] = {m: {s: [] for s in PART_SLOTS} for m in DUAL_CAMERA_MODES}
    part_sheets: dict[tuple[str, str, str], str] = {}

    # paired_parts.csv is the sole authoritative selectable-part catalog in the
    # newest master pack. One row provides both camera sheets for one part_id.
    for row in _rows("paired_parts.csv"):
        slot = str(row.get("slot", "")).strip()
        part_id = str(row.get("part_id", "")).strip()
        if slot not in PART_SLOTS or not part_id:
            continue
        if not _truthy(row.get("paired"), True) or not _truthy(row.get("selectable"), True):
            continue
        for mode, field in (("isometric", "isometric_sheet"), ("topdown", "topdown_sheet")):
            sheet = str(row.get(field, "")).strip()
            if not sheet:
                continue
            part_sheets[(mode, slot, part_id)] = sheet
            if part_id not in parts_by_mode[mode][slot]:
                parts_by_mode[mode][slot].append(part_id)

    customization_presets: dict[str, dict[str, str]] = {}
    profile_names: dict[str, str] = {}
    for row in _rows("customization_presets.csv"):
        pid = str(row.get("preset_id", "")).strip()
        if not pid:
            continue
        customization_presets[pid] = row
        profile_names[pid] = pid.replace("_", " ").title()

    dual_parts: dict[str, list[str]] = {}
    for slot in PART_SLOTS:
        top = parts_by_mode["topdown"][slot]
        iso = set(parts_by_mode["isometric"][slot])
        dual_parts[slot] = [part for part in top if part in iso]
    dual_parts["accessory"] = ["none"] + [p for p in dual_parts.get("accessory", []) if p != "none"]

    fluid: dict[tuple[str, str, str], dict[str, str]] = {}
    fluid_profiles_by_mode: dict[str, list[str]] = {m: [] for m in DUAL_CAMERA_MODES}
    for row in _rows("fluid_animations.csv"):
        mode = str(row.get("camera_mode", "")).strip()
        pid = str(row.get("profile_id", "")).strip()
        animation = str(row.get("animation", "")).strip()
        if mode in DUAL_CAMERA_MODES and pid and animation:
            fluid[(mode, pid, animation)] = row
            if pid not in fluid_profiles_by_mode[mode]:
                fluid_profiles_by_mode[mode].append(pid)

    animations = {row.get("animation", ""): row for row in _rows("animations.csv") if row.get("animation")}
    actions = {(row.get("camera_mode", ""), row.get("action", "")): row for row in _rows("action_sheets.csv") if row.get("camera_mode") and row.get("action")}
    weapons = {row.get("weapon_id", ""): row for row in _rows("weapon_catalog.csv") if row.get("weapon_id")}
    compatibility = [row for row in _rows("compatibility_rules.csv") if row.get("rule_type")]

    return {
        "parts_by_mode": parts_by_mode,
        "part_sheets": part_sheets,
        "profile_names": profile_names,
        "customization_presets": customization_presets,
        "dual_parts": dual_parts,
        "fluid": fluid,
        "fluid_profiles_by_mode": fluid_profiles_by_mode,
        "animations": animations,
        "actions": actions,
        "weapons": weapons,
        "compatibility": compatibility,
    }


def profile_parts(profile_id: str, mode: str = "topdown") -> dict[str, str]:
    row = catalog().get("customization_presets", {}).get(profile_id)
    if row is None:
        row = catalog().get("customization_presets", {}).get(DEFAULT_PROFILE, {})
    return {slot: (str(row.get(slot, "none")).strip() or "none") for slot in PART_SLOTS}


def default_character() -> dict:
    result = profile_parts(DEFAULT_PROFILE, "topdown")
    result["profile"] = DEFAULT_PROFILE
    # Legacy numeric fields stay in packets/DB for painless migration from old accounts.
    result.update({"skin_tone": 2, "hair_style": 1, "hair_color": 1, "top_color": 0, "pants_color": 0})
    return result


def _safe_choice(slot: str, raw: object, default: str) -> str:
    options = catalog()["dual_parts"].get(slot, [])
    value = str(raw or "").strip()
    if value in options:
        return value
    return default if default in options or not options else options[0]


def _rule_allowed(rule_type: str, left: str, right: str) -> bool:
    for row in catalog().get("compatibility", []):
        if row.get("rule_type") == rule_type and row.get("left_id") == left and row.get("right_id") == right:
            return _truthy(row.get("allowed"), False)
    return True


def _compatible_rights(rule_type: str, left: str, slot: str) -> list[str]:
    valid = set(catalog()["dual_parts"].get(slot, []))
    candidates: list[str] = []
    for row in catalog().get("compatibility", []):
        if row.get("rule_type") != rule_type or row.get("left_id") != left or not _truthy(row.get("allowed"), False):
            continue
        right = str(row.get("right_id", "")).strip()
        if right in valid:
            candidates.append(right)
    return candidates


def apply_compatibility(parts: dict[str, str]) -> dict[str, str]:
    """Deterministically repair combinations forbidden by the master-pack CSV."""
    out = dict(parts)
    head = out.get("head", "none")
    top = out.get("top", "none")
    if not _rule_allowed("head_top", head, top):
        preferred = "motorcycle_jacket" if head == "motorcycle_helmet" else profile_parts(DEFAULT_PROFILE).get("top", "tshirt_blue")
        candidates = _compatible_rights("head_top", head, "top")
        if preferred in candidates:
            out["top"] = preferred
        elif candidates:
            out["top"] = candidates[0]
        else:
            out["head"] = profile_parts(DEFAULT_PROFILE).get("head", "curly_short")

    accessory = out.get("accessory", "none")
    head = out.get("head", "none")
    if not _rule_allowed("accessory_head", accessory, head):
        out["accessory"] = "none"
    return out


def matching_preset(parts: dict[str, str]) -> str | None:
    for pid, row in catalog().get("customization_presets", {}).items():
        if all((parts.get(slot, "none") or "none") == (row.get(slot, "none") or "none") for slot in PART_SLOTS):
            return pid
    return None


def matching_profile(parts: dict[str, str], mode: str = "topdown") -> str | None:
    """Return a dedicated fluid-profile ID for an exact tested preset, if available."""
    preset = matching_preset(parts)
    if not preset:
        return None
    fluid_pid = PRESET_TO_FLUID_PROFILE.get(preset)
    if fluid_pid and fluid_pid in catalog().get("fluid_profiles_by_mode", {}).get(mode, []):
        return fluid_pid
    return None


def normalize_character(raw: dict | None) -> dict:
    src = raw if isinstance(raw, dict) else {}
    default = default_character()

    has_new = any(str(src.get(k, "")).strip() for k in ("profile", "head", "top", "bottom", "footwear", "accessory", "body"))
    if has_new:
        requested_profile = str(src.get("profile", "")).strip()
        valid_named = set(preset_options())
        base = profile_parts(requested_profile if requested_profile in valid_named else DEFAULT_PROFILE, "topdown")
        result = {slot: _safe_choice(slot, src.get(slot), base.get(slot, "none")) for slot in PART_SLOTS}
        result = apply_compatibility(result)
        matched = matching_preset(result)
        result["profile"] = matched or "custom"
    else:
        try:
            legacy_index = int(src.get("top_color", default["top_color"])) % len(LEGACY_PROFILE_ORDER)
        except (TypeError, ValueError):
            legacy_index = 0
        pid = LEGACY_PROFILE_ORDER[legacy_index]
        result = profile_parts(pid, "topdown")
        result["profile"] = pid

    legacy_defaults = {k: int(default[k]) for k in LEGACY_KEYS}
    legacy_limits = {"skin_tone": 5, "hair_style": 5, "hair_color": 6, "top_color": 8, "pants_color": 6}
    for key in LEGACY_KEYS:
        try:
            value = int(src.get(key, legacy_defaults[key]))
        except (TypeError, ValueError):
            value = legacy_defaults[key]
        result[key] = max(0, min(legacy_limits[key] - 1, value))
    return result


def display_label(part_id: str) -> str:
    if part_id == "none":
        return "None"
    return str(part_id).replace("_", " ").title()


def custom_options() -> dict[str, list[str]]:
    return {slot: list(catalog()["dual_parts"].get(slot, [])) for slot in CUSTOM_SLOTS}


def preset_options() -> list[str]:
    return list(catalog().get("customization_presets", {}).keys())
