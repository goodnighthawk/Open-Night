from __future__ import annotations

from collections.abc import Iterable


def build_spatial_grid(items: Iterable, cell_size: float, x_attr: str = "x", y_attr: str = "y") -> dict[tuple[int, int], list]:
    cell = max(1.0, float(cell_size))
    grid: dict[tuple[int, int], list] = {}
    for item in items:
        x = float(getattr(item, x_attr))
        y = float(getattr(item, y_attr))
        grid.setdefault((int(x // cell), int(y // cell)), []).append(item)
    return grid


def nearby_from_grid(item, grid: dict[tuple[int, int], list], cell_size: float, radius_cells: int = 1, x_attr: str = "x", y_attr: str = "y") -> list:
    cell = max(1.0, float(cell_size))
    x = float(getattr(item, x_attr))
    y = float(getattr(item, y_attr))
    cx, cy = int(x // cell), int(y // cell)
    out: list = []
    r = max(0, int(radius_cells))
    for yy in range(cy - r, cy + r + 1):
        for xx in range(cx - r, cx + r + 1):
            out.extend(grid.get((xx, yy), ()))
    return out


def nearby_at(x: float, y: float, grid: dict[tuple[int, int], list], cell_size: float, radius_cells: int = 1) -> list:
    cell = max(1.0, float(cell_size))
    cx, cy = int(float(x) // cell), int(float(y) // cell)
    out: list = []
    r = max(0, int(radius_cells))
    for yy in range(cy - r, cy + r + 1):
        for xx in range(cx - r, cx + r + 1):
            out.extend(grid.get((xx, yy), ()))
    return out
