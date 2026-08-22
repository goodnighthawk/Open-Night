from __future__ import annotations

"""Three-layer catalog for the grungy 90-degree top-down character pack."""

from functools import lru_cache
from pathlib import Path

from portable_paths import APP_DIR


BUNDLED_ROOT = APP_DIR / "assets" / "characters" / "grunge_topdown"
PART_SLOTS = ("hat", "head", "body")
CUSTOM_SLOTS = PART_SLOTS
DEFAULT_PROFILE = "grunge_01"

HATS = ("none",) + tuple(f"hat_{index:02d}" for index in range(1, 9))
HEADS = tuple(f"head_{index:02d}" for index in range(1, 9))
BODIES = tuple(f"body_{index:02d}" for index in range(1, 9))
PROFILES = tuple(f"grunge_{index:02d}" for index in range(1, 9))


def pack_root() -> Path:
    return BUNDLED_ROOT


@lru_cache(maxsize=1)
def catalog() -> dict:
    presets = {
        profile: {
            "profile": profile,
            "hat": f"hat_{index:02d}",
            "head": f"head_{index:02d}",
            "body": f"body_{index:02d}",
        }
        for index, profile in enumerate(PROFILES, 1)
    }
    return {
        "profile_names": {profile: f"Grunge {index:02d}" for index, profile in enumerate(PROFILES, 1)},
        "customization_presets": presets,
        "dual_parts": {"hat": list(HATS), "head": list(HEADS), "body": list(BODIES)},
        "parts_by_mode": {"topdown": {"hat": list(HATS), "head": list(HEADS), "body": list(BODIES)}},
    }


def profile_parts(profile_id: str, mode: str = "topdown") -> dict[str, str]:
    del mode
    return dict(catalog()["customization_presets"].get(profile_id, catalog()["customization_presets"][DEFAULT_PROFILE]))


def default_character() -> dict:
    result = profile_parts(DEFAULT_PROFILE)
    # Historical fields remain in network/database records during migration;
    # no historical image is loaded or rendered from them.
    result.update({
        "accessory": result["hat"], "top": "none", "bottom": "none", "footwear": "none",
        "skin_tone": 0, "hair_style": 0, "hair_color": 0, "top_color": 0, "pants_color": 0,
    })
    return result


def _choice(raw: object, options: tuple[str, ...], fallback: str) -> str:
    value = str(raw or "").strip()
    return value if value in options else fallback


def _legacy_index(src: dict, key: str, fallback: int = 0) -> int:
    try:
        return int(src.get(key, fallback)) % 8
    except (TypeError, ValueError):
        return fallback % 8


def normalize_character(raw: dict | None) -> dict:
    src = raw if isinstance(raw, dict) else {}
    requested_profile = str(src.get("profile", "")).strip()
    if requested_profile in PROFILES:
        base = profile_parts(requested_profile)
    else:
        # Stable migration: old accounts keep variety without retaining any
        # dependency on their former top/bottom/footwear sprite identifiers.
        body_index = _legacy_index(src, "top_color")
        head_index = _legacy_index(src, "skin_tone")
        hat_index = _legacy_index(src, "hair_style")
        base = {
            "body": BODIES[body_index],
            "head": HEADS[head_index],
            "hat": HATS[hat_index + 1],
        }

    body = _choice(src.get("body"), BODIES, base["body"])
    head = _choice(src.get("head"), HEADS, base["head"])
    # The old accessory DB column temporarily carries the new hat ID.
    hat = _choice(src.get("hat", src.get("accessory")), HATS, base["hat"])
    matched = next((profile for profile in PROFILES if profile_parts(profile)["body"] == body
                    and profile_parts(profile)["head"] == head and profile_parts(profile)["hat"] == hat), None)
    result = {
        "profile": matched or "custom", "hat": hat, "head": head, "body": body,
        "accessory": hat, "top": "none", "bottom": "none", "footwear": "none",
    }
    for key, fallback in (("skin_tone", 0), ("hair_style", 0), ("hair_color", 0), ("top_color", 0), ("pants_color", 0)):
        try:
            result[key] = max(0, min(255, int(src.get(key, fallback))))
        except (TypeError, ValueError):
            result[key] = fallback
    return result


def matching_profile(parts: dict[str, str], mode: str = "topdown") -> str | None:
    del mode
    selected = normalize_character({"profile": "custom", **(parts or {})})
    for profile in PROFILES:
        preset = profile_parts(profile)
        if all(selected[slot] == preset[slot] for slot in PART_SLOTS):
            return profile
    return None


def display_label(part_id: str) -> str:
    if part_id == "none":
        return "None"
    return str(part_id).replace("_", " ").title()


def custom_options() -> dict[str, list[str]]:
    return {"hat": list(HATS), "head": list(HEADS), "body": list(BODIES)}


def preset_options() -> list[str]:
    return list(PROFILES)
