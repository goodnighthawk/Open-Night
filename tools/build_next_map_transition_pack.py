from __future__ import annotations

"""Extract the approved transition and traffic masters into runtime sprites.

The source sheets are approval artifacts and remain untouched.  Runtime PNGs and
their companion catalog are rebuilt deterministically from only the four approved
masters named below.
"""

from collections import deque
import json
from pathlib import Path

import numpy as np
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "assets" / "generated_v4_transitions" / "source"
OUTPUT = ROOT / "assets" / "generated_v4_transitions"
CATALOG = ROOT / "assets" / "grid_v100" / "generated_transition_objects.json"

APPROVED_MASTERS = {
    "building": SOURCE / "approved_building_transitions.png",
    "buzzer": SOURCE / "approved_buzzer_and_signal.png",
    "fire_escape": SOURCE / "approved_fire_escape_ladder.png",
    "traffic": SOURCE / "approved_traffic_signal_matrix.png",
}


def _tight_alpha_crop(image: Image.Image, region: tuple[int, int, int, int], padding: int = 6) -> Image.Image:
    """Crop one already-transparent master region without retaining sheet debris."""
    left, top, right, bottom = region
    part = image.crop(region).convert("RGBA")
    alpha = np.asarray(part.getchannel("A"))
    ys, xs = np.nonzero(alpha > 10)
    if not len(xs):
        raise RuntimeError(f"approved source region is empty: {region}")
    x0 = max(0, int(xs.min()) - padding)
    y0 = max(0, int(ys.min()) - padding)
    x1 = min(part.width, int(xs.max()) + padding + 1)
    y1 = min(part.height, int(ys.max()) + padding + 1)
    return part.crop((x0, y0, x1, y1))


def _checkerboard_to_alpha(cell: Image.Image) -> Image.Image:
    """Remove the matrix's baked pale checkerboard while retaining metal highlights.

    The checker also appears in fully enclosed negative spaces between the pole,
    arm and pedestrian box, so border flood-fill alone is insufficient.  The
    approved background is uniformly pale and neutral; the steel highlights are
    darker or chromatic.  Keying only that narrow neutral range preserves the
    blue-white metal edge light and all internal lamp detail.
    """
    rgb = np.asarray(cell.convert("RGB"), dtype=np.uint8)
    high = rgb.max(axis=2).astype(np.int16)
    low = rgb.min(axis=2).astype(np.int16)
    candidate = (low >= 228) & ((high - low) <= 9)
    # Neutral highlight islands enclosed inside the artwork are legitimate pale
    # metal.  Large neutral components (including enclosed checker cavities) are
    # background.  This restores the pole's narrow vertical highlight without
    # keeping the broad checker area beside it.
    height, width = candidate.shape
    visited = np.zeros((height, width), dtype=bool)
    preserve = np.zeros((height, width), dtype=bool)
    for start_y, start_x in zip(*np.nonzero(candidate & ~visited)):
        if visited[start_y, start_x]:
            continue
        queue: deque[tuple[int, int]] = deque([(int(start_x), int(start_y))])
        visited[start_y, start_x] = True
        component: list[tuple[int, int]] = []
        touches_border = False
        while queue:
            x, y = queue.popleft()
            component.append((x, y))
            touches_border |= x == 0 or y == 0 or x == width - 1 or y == height - 1
            for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                if 0 <= nx < width and 0 <= ny < height and candidate[ny, nx] and not visited[ny, nx]:
                    visited[ny, nx] = True
                    queue.append((nx, ny))
        if not touches_border and len(component) <= 1500:
            for x, y in component:
                preserve[y, x] = True
    alpha = np.where(candidate & ~preserve, 0, 255).astype(np.uint8)
    rgba = np.dstack((rgb, alpha))
    return Image.fromarray(rgba, "RGBA")


def _traffic_cells(matrix: Image.Image) -> list[Image.Image]:
    widths = [matrix.width // 3, matrix.width // 3, matrix.width - 2 * (matrix.width // 3)]
    heights = [matrix.height // 2, matrix.height - matrix.height // 2]
    cells: list[Image.Image] = []
    y = 0
    for height in heights:
        x = 0
        for width in widths:
            cells.append(_checkerboard_to_alpha(matrix.crop((x, y, x + width, y + height))))
            x += width
        y += height
    return cells


def _aligned_traffic_sprites(cells: list[Image.Image], padding: int = 8) -> tuple[list[Image.Image], tuple[int, int]]:
    """Align all traffic states to the base/pole pivot on one identical canvas."""
    measurements: list[tuple[Image.Image, int, int, tuple[int, int, int, int]]] = []
    for cell in cells:
        alpha = np.asarray(cell.getchannel("A"))
        ys, xs = np.nonzero(alpha > 0)
        if not len(xs):
            raise RuntimeError("traffic matrix contains an empty state")
        bbox = (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)
        bottom_y = bbox[3] - 1
        bottom_band = (ys >= bottom_y - 8)
        pivot_x = int(round(float(np.median(xs[bottom_band])))) if bottom_band.any() else (bbox[0] + bbox[2]) // 2
        measurements.append((cell, pivot_x, bottom_y, bbox))

    left = max(pivot_x - bbox[0] for _, pivot_x, _, bbox in measurements)
    right = max(bbox[2] - pivot_x for _, pivot_x, _, bbox in measurements)
    above = max(pivot_y - bbox[1] for _, _, pivot_y, bbox in measurements)
    below = max(bbox[3] - pivot_y for _, _, pivot_y, bbox in measurements)
    canvas_width = left + right + padding * 2
    canvas_height = above + below + padding * 2
    common_pivot = (left + padding, above + padding)
    aligned: list[Image.Image] = []
    for cell, pivot_x, pivot_y, _bbox in measurements:
        canvas = Image.new("RGBA", (canvas_width, canvas_height), (0, 0, 0, 0))
        canvas.alpha_composite(cell, (common_pivot[0] - pivot_x, common_pivot[1] - pivot_y))
        aligned.append(canvas)
    return aligned, common_pivot


def _save(name: str, image: Image.Image) -> str:
    path = OUTPUT / f"{name}.png"
    image.save(path, optimize=True)
    return path.relative_to(ROOT).as_posix()


def build() -> dict:
    for path in APPROVED_MASTERS.values():
        if not path.is_file():
            raise FileNotFoundError(f"missing approved transition master: {path}")
    OUTPUT.mkdir(parents=True, exist_ok=True)

    building = Image.open(APPROVED_MASTERS["building"]).convert("RGBA")
    buzzer_sheet = Image.open(APPROVED_MASTERS["buzzer"]).convert("RGBA")
    ladder_sheet = Image.open(APPROVED_MASTERS["fire_escape"]).convert("RGBA")

    # Regions deliberately exclude the unapproved full fire escape in the
    # building sheet and the unapproved signal iteration in the buzzer sheet.
    extracted = {
        "entrance_door": _tight_alpha_crop(building, (135, 0, 625, 555)),
        "roof_access_door": _tight_alpha_crop(building, (120, 565, 625, 1148)),
        "elevator_transition": _tight_alpha_crop(building, (715, 565, 1370, 1148)),
        "entrance_buzzer": _tight_alpha_crop(buzzer_sheet, (120, 80, 490, 900)),
        "fire_escape_ladder": _tight_alpha_crop(ladder_sheet, (390, 0, 820, 1280)),
    }
    images = {name: _save(name, image) for name, image in extracted.items()}

    traffic_names = (
        "traffic_red_not_clear", "traffic_yellow_not_clear", "traffic_green_not_clear",
        "traffic_red_clear", "traffic_yellow_clear", "traffic_green_clear",
    )
    matrix = Image.open(APPROVED_MASTERS["traffic"]).convert("RGB")
    traffic, source_pivot = _aligned_traffic_sprites(_traffic_cells(matrix))
    for name, image in zip(traffic_names, traffic):
        images[name] = _save(name, image)

    signal_native = (128, 176)
    signal_pivot = (
        int(round(source_pivot[0] * signal_native[0] / traffic[0].width)),
        int(round(source_pivot[1] * signal_native[1] / traffic[0].height)),
    )
    objects = {
        "entrance_door": {
            "image": images["entrance_door"], "kind": "transition_art", "layer": "ground", "z": 170,
            "native_width_px": 112, "native_height_px": 144, "pivot_x_px": 56, "pivot_y_px": 140,
            "optional": True,
        },
        "roof_access_door": {
            "image": images["roof_access_door"], "kind": "transition_art", "layer": "roof", "z": 170,
            "native_width_px": 116, "native_height_px": 140, "pivot_x_px": 58, "pivot_y_px": 70,
            "optional": True,
        },
        "elevator_transition": {
            "image": images["elevator_transition"], "kind": "transition_art", "layer": "ground", "z": 170,
            "native_width_px": 132, "native_height_px": 120, "pivot_x_px": 66, "pivot_y_px": 112,
            "optional": True,
        },
        "entrance_buzzer": {
            "image": images["entrance_buzzer"], "kind": "interaction_art", "layer": "ground", "z": 172,
            "native_width_px": 24, "native_height_px": 58, "pivot_x_px": 12, "pivot_y_px": 54,
            "optional": True,
        },
        "fire_escape_ladder": {
            "image": images["fire_escape_ladder"], "kind": "transition_art", "layer": "ground", "z": 171,
            "native_width_px": 62, "native_height_px": 216, "pivot_x_px": 31, "pivot_y_px": 108,
            "optional": True,
        },
    }
    for name in traffic_names:
        objects[name] = {
            "image": images[name], "kind": "dynamic_signal_art", "layer": "ground", "z": 176,
            "native_width_px": signal_native[0], "native_height_px": signal_native[1],
            "pivot_x_px": signal_pivot[0], "pivot_y_px": signal_pivot[1],
            "optional": True,
        }

    # Backward-compatible object IDs are catalog aliases, so older maps receive
    # approved art without any renderer or generator path special cases.
    objects["placeholder_street_door"] = dict(objects["entrance_door"])
    objects["placeholder_roof_hatch"] = dict(objects["roof_access_door"])
    objects["placeholder_fire_escape"] = dict(objects["fire_escape_ladder"])

    payload = {
        "version": 1,
        "source_policy": "approved_masters_only",
        "approved_masters": [path.relative_to(ROOT).as_posix() for path in APPROVED_MASTERS.values()],
        "objects": objects,
        "traffic_signal_states": list(traffic_names),
        "traffic_canvas_px": list(traffic[0].size),
        "traffic_source_pivot_px": list(source_pivot),
        "traffic_runtime_pivot_px": list(signal_pivot),
    }
    CATALOG.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


if __name__ == "__main__":
    result = build()
    print(
        "NEXT_MAP_TRANSITION_PACK_OK "
        f"objects={len(result['objects'])} states={len(result['traffic_signal_states'])} "
        f"canvas={result['traffic_canvas_px']} pivot={result['traffic_runtime_pivot_px']}"
    )
