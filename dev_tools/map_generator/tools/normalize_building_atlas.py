from __future__ import annotations

import argparse
import csv
from collections import deque
from pathlib import Path

from PIL import Image, ImageFilter


COLS = 4
ROWS = 4


def _largest_component_mask(cell: Image.Image) -> Image.Image:
    """Extract one connected sprite from an opaque light/checker background."""
    rgba = cell.convert("RGBA")
    width, height = rgba.size
    pixels = rgba.load()
    foreground = bytearray(width * height)
    for y in range(height):
        for x in range(width):
            red, green, blue, _ = pixels[x, y]
            low = min(red, green, blue)
            chroma = max(red, green, blue) - low
            # Image generation sometimes paints a pale checkerboard instead of
            # returning alpha. Building materials and attached shadows are both
            # darker or more chromatic than that neutral background.
            if not (low >= 220 and chroma <= 20):
                foreground[y * width + x] = 1

    seen = bytearray(width * height)
    largest: list[int] = []
    for start, occupied in enumerate(foreground):
        if not occupied or seen[start]:
            continue
        component: list[int] = []
        queue = deque([start])
        seen[start] = 1
        while queue:
            index = queue.popleft()
            component.append(index)
            x = index % width
            y = index // width
            for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                if 0 <= nx < width and 0 <= ny < height:
                    neighbour = ny * width + nx
                    if foreground[neighbour] and not seen[neighbour]:
                        seen[neighbour] = 1
                        queue.append(neighbour)
        if len(component) > len(largest):
            largest = component

    mask = Image.new("L", (width, height), 0)
    mask_pixels = mask.load()
    for index in largest:
        mask_pixels[index % width, index // width] = 255
    # Bright skylights and pale roof membranes can be fully enclosed by the
    # darker roof component. They are sprite detail, not exterior background.
    # Flood the inverse mask from the cell border and fill every unreachable
    # zero-valued island before antialiasing the silhouette.
    exterior = bytearray(width * height)
    queue: deque[int] = deque()
    for x in range(width):
        for y in (0, height - 1):
            index = y * width + x
            if not mask_pixels[x, y] and not exterior[index]:
                exterior[index] = 1
                queue.append(index)
    for y in range(height):
        for x in (0, width - 1):
            index = y * width + x
            if not mask_pixels[x, y] and not exterior[index]:
                exterior[index] = 1
                queue.append(index)
    while queue:
        index = queue.popleft()
        x = index % width
        y = index // width
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if 0 <= nx < width and 0 <= ny < height:
                neighbour = ny * width + nx
                if not mask_pixels[nx, ny] and not exterior[neighbour]:
                    exterior[neighbour] = 1
                    queue.append(neighbour)
    for index, outside in enumerate(exterior):
        if not outside:
            mask_pixels[index % width, index // width] = 255
    # Pull the matte slightly inside the painted checkerboard edge, then restore
    # sub-pixel antialiasing. This avoids pale halos on dark asphalt at night.
    return mask.filter(ImageFilter.MinFilter(3)).filter(ImageFilter.GaussianBlur(0.55))


def normalize(source: Path, target: Path, report: Path) -> None:
    atlas = Image.open(source).convert("RGBA")
    if atlas.width % COLS or atlas.height % ROWS:
        raise SystemExit(f"Atlas must divide evenly into {COLS}x{ROWS}: {atlas.size}")
    cell_width = atlas.width // COLS
    cell_height = atlas.height // ROWS
    output = Image.new("RGBA", atlas.size, (0, 0, 0, 0))
    metrics = []

    for cell_index in range(COLS * ROWS):
        column = cell_index % COLS
        row = cell_index // COLS
        box = (
            column * cell_width,
            row * cell_height,
            (column + 1) * cell_width,
            (row + 1) * cell_height,
        )
        sprite = atlas.crop(box)
        alpha = _largest_component_mask(sprite)
        bounds = alpha.point(lambda value: 255 if value >= 32 else 0).getbbox()
        if bounds is None:
            raise SystemExit(f"Cell {cell_index} has no recoverable sprite")
        sprite.putalpha(alpha)
        output.alpha_composite(sprite, (box[0], box[1]))
        width = bounds[2] - bounds[0]
        height = bounds[3] - bounds[1]
        metrics.append(
            {
                "cell": cell_index,
                "bbox_x": bounds[0],
                "bbox_y": bounds[1],
                "bbox_w": width,
                "bbox_h": height,
                "width_ratio": round(width / cell_width, 4),
                "height_ratio": round(height / cell_height, 4),
                "occupied_bbox_ratio": round((width * height) / (cell_width * cell_height), 4),
            }
        )

    widths = [int(row["bbox_w"]) for row in metrics]
    heights = [int(row["bbox_h"]) for row in metrics]
    if max(widths) / min(widths) > 1.55 or max(heights) / min(heights) > 1.55:
        raise SystemExit(
            "Sprite footprint scale audit failed: "
            f"width range {min(widths)}..{max(widths)}, height range {min(heights)}..{max(heights)}"
        )

    target.parent.mkdir(parents=True, exist_ok=True)
    output.save(target, optimize=True)
    report.parent.mkdir(parents=True, exist_ok=True)
    with report.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(metrics[0]))
        writer.writeheader()
        writer.writerows(metrics)
    print(
        f"PASS {source.name}: 16 cells, true alpha, "
        f"width {min(widths)}..{max(widths)}, height {min(heights)}..{max(heights)}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Recover true alpha and audit a 4x4 building atlas")
    parser.add_argument("source", type=Path)
    parser.add_argument("target", type=Path)
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    normalize(args.source, args.target, args.report)


if __name__ == "__main__":
    main()
